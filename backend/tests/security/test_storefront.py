"""Storefront draft workflows, authorization, and tenant isolation (M4B).

Extends the permanent isolation matrix (docs/04) to `storefront_versions`
and proves the ADR-020 service rules through direct service calls against
the migrated schema: the §5 first-draft/create-intent contract, §6
optimistic concurrency, the D-5 exact-no-op suppression, the §8 closed
lifecycle gate, and the §10/D-6 validate-before-claim media ordering.
The HTTP matrix over the same behavior lands with the routers.
"""

import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    ApiError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.domains.businesses.queries import lock_business_status
from app.domains.identity.actor import ActorContext, AuthenticatedUser
from app.domains.storefront import service as storefront_service
from app.domains.storefront.composition import StorefrontConfig, parse_config
from app.domains.storefront.schemas import DraftPut
from tests.security.conftest import CreateBusiness, CreateMembership, CreateUser

OWNER = "owner@example.com"
MANAGER = "manager@example.com"
STAFF = "staff@example.com"
INTRUDER = "intruder-owner@example.com"
PLATFORM_ADMIN = "admin@example.com"

CHECKSUM = "0123456789abcdef" * 4


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=migrated_engine)
    session = factory()
    yield session
    session.rollback()
    session.close()


def _actor(user_id: uuid.UUID, *, is_platform_admin: bool = False) -> ActorContext:
    return ActorContext(
        user=AuthenticatedUser(
            id=user_id,
            email=OWNER,
            display_name="Test User",
            is_platform_admin=is_platform_admin,
        ),
        session_id=uuid.uuid4(),
        csrf_token="test-csrf",
    )


def _config(
    sections: list[dict[str, Any]] | None = None, accent: str = "#a34b2a"
) -> StorefrontConfig:
    return parse_config(
        {"schema_version": 1, "theme": {"accent": accent}, "sections": sections or []}
    )


def _hero(media_id: uuid.UUID | None = None, heading: str = "Welcome") -> dict[str, Any]:
    props: dict[str, Any] = {"heading": heading}
    if media_id is not None:
        props["image"] = {"media_id": str(media_id)}
    return {"id": "hero-main", "type": "hero", "enabled": True, "props": props}


def _gallery(media_ids: list[uuid.UUID]) -> dict[str, Any]:
    return {
        "id": "gallery-main",
        "type": "gallery",
        "enabled": True,
        "props": {"images": [{"media_id": str(media_id)} for media_id in media_ids]},
    }


def _insert_media_asset(
    engine: Engine,
    business_id: uuid.UUID,
    *,
    status: str = "pending",
    expires_hours: float = 48,
) -> uuid.UUID:
    """Seed one asset row directly (fixture setup, not the flow under test)."""
    asset_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO media_assets (id, business_id, kind, status,"
                " pending_expires_at, original_filename, declared_content_type,"
                " source_format, width, height, byte_size, checksum_sha256)"
                " VALUES (:id, :bid, 'image', :status,"
                " CASE WHEN :status = 'pending'"
                "   THEN now() + make_interval(hours => :hours) ELSE NULL END,"
                " 'photo.jpg', 'image/jpeg', 'jpeg', 800, 600, 12345, :checksum)"
            ),
            {
                "id": asset_id,
                "bid": business_id,
                "status": status,
                "hours": expires_hours,
                "checksum": CHECKSUM,
            },
        )
    return asset_id


def _asset_status(engine: Engine, asset_id: uuid.UUID) -> tuple[str, bool]:
    """(status, has_pending_expiry) straight from the database."""
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT status, pending_expires_at FROM media_assets WHERE id = :id"),
            {"id": asset_id},
        ).one()
    return str(row[0]), row[1] is not None


def _version_rows(engine: Engine, business_id: uuid.UUID) -> list[dict[str, Any]]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                "SELECT state, version_number, design_variant, lock_version,"
                " source_version_id, config FROM storefront_versions"
                " WHERE business_id = :bid ORDER BY created_at, state"
            ),
            {"bid": business_id},
        ).mappings()
        return [dict(row) for row in rows]


def _draft_updated_at(engine: Engine, business_id: uuid.UUID) -> Any:
    with engine.begin() as connection:
        return connection.execute(
            text(
                "SELECT updated_at FROM storefront_versions"
                " WHERE business_id = :bid AND state = 'draft'"
            ),
            {"bid": business_id},
        ).scalar_one()


class TestOverviewRead:
    def test_absence_reads_as_absent_and_creates_nothing(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)

        overview = storefront_service.get_overview(db, _actor(owner_id), business)

        assert overview.draft is None
        assert overview.published is None
        assert _version_rows(migrated_engine, business) == []

    def test_closed_business_remains_readable(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business(status="closed")
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)

        overview = storefront_service.get_overview(db, _actor(owner_id), business)

        assert overview.draft is None


class TestDraftCreate:
    @pytest.mark.parametrize("status", ["provisioning", "active", "suspended"])
    def test_create_intent_creates_the_first_draft(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        status: str,
    ) -> None:
        business = create_business(status=status)
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        config = _config([_hero()])

        view = storefront_service.put_draft(db, _actor(owner_id), business, DraftPut(config=config))

        assert view.lock_version == 0
        assert view.design_variant.value == "classic"
        assert view.source_version_id is None
        assert view.config == config
        rows = _version_rows(migrated_engine, business)
        assert len(rows) == 1
        assert rows[0]["state"] == "draft"
        assert rows[0]["version_number"] is None
        assert rows[0]["lock_version"] == 0

    def test_create_intent_conflicts_when_a_draft_exists(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(db, actor, business, DraftPut(config=_config([_hero()])))

        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "conflict"
        assert excinfo.value.details == {"lock_version": 0}
        db.rollback()
        # Never an overwrite (§5.5): the stored draft is the original.
        rows = _version_rows(migrated_engine, business)
        assert len(rows) == 1
        assert rows[0]["config"]["sections"] == []

    def test_closed_business_rejects_creation(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business(status="closed")
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(db, _actor(owner_id), business, DraftPut(config=_config()))

        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "invalid_state"


class TestDraftUpdate:
    def test_exact_lock_replaces_and_increments(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))

        updated = storefront_service.put_draft(
            db,
            actor,
            business,
            DraftPut(config=_config([_hero()]), expected_lock_version=0),
        )

        assert updated.lock_version == 1
        assert [section.type.value for section in updated.config.sections] == ["hero"]

    def test_stale_lock_conflicts_with_the_current_value(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))
        storefront_service.put_draft(
            db, actor, business, DraftPut(config=_config([_hero()]), expected_lock_version=0)
        )

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db,
                actor,
                business,
                DraftPut(config=_config(), expected_lock_version=0),
            )

        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "conflict"
        assert excinfo.value.details == {"lock_version": 1}

    def test_update_intent_without_a_draft_conflicts(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db,
                _actor(owner_id),
                business,
                DraftPut(config=_config(), expected_lock_version=0),
            )

        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "conflict"

    def test_exact_noop_is_suppressed(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        config = _config([_hero()])
        storefront_service.put_draft(db, actor, business, DraftPut(config=config))
        before = _draft_updated_at(migrated_engine, business)

        view = storefront_service.put_draft(
            db, actor, business, DraftPut(config=config, expected_lock_version=0)
        )

        # No write, no increment, no updated_at bump (D-5).
        assert view.lock_version == 0
        assert _draft_updated_at(migrated_engine, business) == before


class TestDraftAuthorization:
    def test_staff_cannot_read_or_write(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        staff_id = create_user(STAFF)
        create_membership(business, staff_id, role="staff")
        actor = _actor(staff_id)

        with pytest.raises(PermissionDeniedError):
            storefront_service.get_overview(db, actor, business)
        with pytest.raises(PermissionDeniedError):
            storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))

    def test_manager_can_read_and_write(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        manager_id = create_user(MANAGER)
        create_membership(business, manager_id, role="manager")
        actor = _actor(manager_id)

        view = storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))
        overview = storefront_service.get_overview(db, actor, business)

        assert view.lock_version == 0
        assert overview.draft is not None

    def test_nonmember_and_platform_admin_get_404(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        other_business = create_business(slug="other-kitchen", name="Other Kitchen")
        intruder_id = create_user(INTRUDER)
        create_membership(other_business, intruder_id)
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)

        for actor in (_actor(intruder_id), _actor(admin_id, is_platform_admin=True)):
            with pytest.raises(ResourceNotFoundError):
                storefront_service.get_overview(db, actor, business)
            db.rollback()
            with pytest.raises(ResourceNotFoundError):
                storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))
            db.rollback()


class TestDraftMediaClaiming:
    def test_valid_pending_reference_is_claimed(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        asset = _insert_media_asset(migrated_engine, business)

        storefront_service.put_draft(
            db, _actor(owner_id), business, DraftPut(config=_config([_hero(asset)]))
        )

        status, has_expiry = _asset_status(migrated_engine, asset)
        assert status == "active"
        assert has_expiry is False

    def test_gallery_claims_every_reference(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        first = _insert_media_asset(migrated_engine, business)
        second = _insert_media_asset(migrated_engine, business)

        storefront_service.put_draft(
            db,
            _actor(owner_id),
            business,
            DraftPut(config=_config([_gallery([first, second])])),
        )

        assert _asset_status(migrated_engine, first)[0] == "active"
        assert _asset_status(migrated_engine, second)[0] == "active"

    def test_unknown_reference_rejected_before_any_claim(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        valid = _insert_media_asset(migrated_engine, business)
        missing = uuid.uuid4()

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db,
                _actor(owner_id),
                business,
                DraftPut(config=_config([_gallery([valid, missing])])),
            )
        db.rollback()

        assert excinfo.value.status_code == 422
        assert excinfo.value.code.value == "validation_error"
        assert excinfo.value.details == {"media_ids": [str(missing)]}
        # Validation precedes claiming (§10): the valid asset was NOT
        # promoted, and no draft row was created.
        assert _asset_status(migrated_engine, valid)[0] == "pending"
        assert _version_rows(migrated_engine, business) == []

    def test_foreign_reference_is_indistinguishable_from_unknown(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        other_business = create_business(slug="other-kitchen", name="Other Kitchen")
        foreign_asset = _insert_media_asset(migrated_engine, other_business)
        missing = uuid.uuid4()
        actor = _actor(owner_id)

        with pytest.raises(ApiError) as foreign_exc:
            storefront_service.put_draft(
                db, actor, business, DraftPut(config=_config([_hero(foreign_asset)]))
            )
        db.rollback()
        with pytest.raises(ApiError) as unknown_exc:
            storefront_service.put_draft(
                db, actor, business, DraftPut(config=_config([_hero(missing)]))
            )
        db.rollback()

        # Same status, code, message, and details shape (D-6): a foreign
        # asset and a nonexistent one disclose nothing different.
        assert foreign_exc.value.status_code == unknown_exc.value.status_code == 422
        assert foreign_exc.value.code == unknown_exc.value.code
        assert foreign_exc.value.message == unknown_exc.value.message
        assert foreign_exc.value.details == {"media_ids": [str(foreign_asset)]}
        assert unknown_exc.value.details == {"media_ids": [str(missing)]}
        # The foreign business's asset is untouched.
        assert _asset_status(migrated_engine, foreign_asset)[0] == "pending"

    def test_expired_pending_reference_is_invalid_state(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        expired = _insert_media_asset(migrated_engine, business, expires_hours=-1)

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db, _actor(owner_id), business, DraftPut(config=_config([_hero(expired)]))
            )
        db.rollback()

        # The established claim-path behavior (ADR-017 final correction J).
        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "invalid_state"
        assert _asset_status(migrated_engine, expired)[0] == "pending"
        assert _version_rows(migrated_engine, business) == []

    def test_noop_update_claims_nothing(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        asset = _insert_media_asset(migrated_engine, business)
        actor = _actor(owner_id)
        config = _config([_hero(asset)])
        storefront_service.put_draft(db, actor, business, DraftPut(config=config))
        assert _asset_status(migrated_engine, asset)[0] == "active"
        # Force the asset back to pending; an exact no-op must not re-claim.
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE media_assets SET status = 'pending',"
                    " pending_expires_at = now() + interval '48 hours' WHERE id = :id"
                ),
                {"id": asset},
            )

        storefront_service.put_draft(
            db, actor, business, DraftPut(config=config, expected_lock_version=0)
        )

        assert _asset_status(migrated_engine, asset)[0] == "pending"


class TestFirstDraftRace:
    def test_concurrent_creates_serialize_on_the_business_lock(
        self,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """§5.8/§5.9: creation takes the Business lock first; only the first
        request creates the draft and the second gets the conflict."""
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        session_factory = sessionmaker(bind=migrated_engine)
        session_a = session_factory()
        outcome: dict[str, Any] = {}
        b_started = threading.Event()

        def run_b() -> None:
            session_b = session_factory()
            try:
                b_started.set()
                storefront_service.put_draft(
                    session_b, actor, business, DraftPut(config=_config([_hero()]))
                )
                outcome["result"] = "created"
            except ApiError as exc:
                outcome["result"] = (exc.status_code, exc.code.value, exc.details)
            except Exception as exc:  # pragma: no cover - diagnostic only
                outcome["result"] = ("unexpected", type(exc).__name__)
            finally:
                session_b.rollback()
                session_b.close()

        thread = threading.Thread(target=run_b)
        try:
            # A: take the Business lock, create the draft uncommitted.
            assert lock_business_status(session_a, business) == "provisioning"
            session_a.execute(
                text(
                    "INSERT INTO storefront_versions (id, business_id, state,"
                    " version_number, schema_version, design_variant, config,"
                    " lock_version) VALUES (gen_random_uuid(), :bid, 'draft', NULL,"
                    " 1, 'classic',"
                    ' \'{"schema_version": 1, "theme": {"accent": "#a34b2a"},'
                    ' "sections": []}\'::jsonb, 0)'
                ),
                {"bid": business},
            )
            thread.start()
            b_started.wait(timeout=5)
            time.sleep(0.2)  # let B reach (and block on) the Business lock
            session_a.commit()
        finally:
            session_a.close()
            thread.join(timeout=10)

        assert outcome["result"] == (409, "conflict", {"lock_version": 0})
        rows = _version_rows(migrated_engine, business)
        assert len(rows) == 1
        assert rows[0]["state"] == "draft"
