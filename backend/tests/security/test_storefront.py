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
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    ApiError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.domains.businesses.queries import lock_business_status
from app.domains.identity.actor import ActorContext, AuthenticatedUser
from app.domains.media import service as media_service
from app.domains.storefront import service as storefront_service
from app.domains.storefront.composition import StorefrontConfig, parse_config
from app.domains.storefront.schemas import (
    DesignAssignment,
    DraftPut,
    PublishRequest,
    RestoreRequest,
)
from app.domains.storefront.variants import DesignVariant
from tests.security.conftest import (
    BROWSER_HEADERS,
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

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
    sections: list[dict[str, Any]] | None = None,
    accent: str = "#a34b2a",
    *,
    logo: uuid.UUID | None = None,
    palette: str | None = None,
    type_pairing: str | None = None,
) -> StorefrontConfig:
    theme: dict[str, Any] = {"accent": accent}
    if logo is not None:
        theme["logo"] = {"media_id": str(logo)}
    if palette is not None:
        theme["palette"] = palette
    if type_pairing is not None:
        theme["type_pairing"] = type_pairing
    return parse_config({"schema_version": 1, "theme": theme, "sections": sections or []})


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


class TestThemeLogoClaiming:
    """The theme logo is claimed exactly like section media (ADR-024 §7).

    The whole point of the document-level collection is that these cases
    need no new rules: the logo travels the same validate-then-claim path,
    so the failure matrix is the established one, proved here for the field
    that lives outside every section.
    """

    def test_a_valid_pending_logo_is_claimed(
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
        logo = _insert_media_asset(migrated_engine, business)

        storefront_service.put_draft(
            db, _actor(owner_id), business, DraftPut(config=_config(logo=logo))
        )

        status, has_expiry = _asset_status(migrated_engine, logo)
        assert status == "active"
        assert has_expiry is False

    def test_a_logo_and_section_media_are_claimed_in_one_pass(
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
        logo = _insert_media_asset(migrated_engine, business)
        hero = _insert_media_asset(migrated_engine, business)
        gallery = _insert_media_asset(migrated_engine, business)

        storefront_service.put_draft(
            db,
            _actor(owner_id),
            business,
            DraftPut(config=_config([_hero(hero), _gallery([gallery])], logo=logo)),
        )

        for asset in (logo, hero, gallery):
            assert _asset_status(migrated_engine, asset)[0] == "active"

    def test_one_asset_used_as_both_logo_and_hero_is_claimed_once(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """De-duplication spans theme and sections: nothing forbids reusing
        one asset, and the claim must not run twice for it."""
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        shared = _insert_media_asset(migrated_engine, business)

        with mock.patch(
            "app.domains.storefront.service.media_service.claim_for_attachment",
            wraps=media_service.claim_for_attachment,
        ) as claim:
            storefront_service.put_draft(
                db,
                _actor(owner_id),
                business,
                DraftPut(config=_config([_hero(shared)], logo=shared)),
            )

        assert claim.call_count == 1
        assert _asset_status(migrated_engine, shared)[0] == "active"

    def test_an_unknown_logo_is_rejected_before_any_claim(
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
        hero = _insert_media_asset(migrated_engine, business)
        missing = uuid.uuid4()

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db,
                _actor(owner_id),
                business,
                DraftPut(config=_config([_hero(hero)], logo=missing)),
            )
        db.rollback()

        assert excinfo.value.status_code == 422
        assert excinfo.value.code.value == "validation_error"
        assert excinfo.value.details == {"media_ids": [str(missing)]}
        # Validation precedes claiming (§10): the co-referenced hero asset
        # was NOT promoted, and no draft row exists.
        assert _asset_status(migrated_engine, hero)[0] == "pending"
        assert _version_rows(migrated_engine, business) == []

    def test_a_foreign_logo_is_indistinguishable_from_an_unknown_one(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """Isolation: another tenant's asset id discloses nothing, and the
        envelope is byte-identical to the unknown-id case."""
        business = create_business()
        other = create_business(slug="other-kitchen", name="Other Kitchen")
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        foreign = _insert_media_asset(migrated_engine, other)

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db, _actor(owner_id), business, DraftPut(config=_config(logo=foreign))
            )
        db.rollback()

        assert excinfo.value.status_code == 422
        assert excinfo.value.code.value == "validation_error"
        assert excinfo.value.details == {"media_ids": [str(foreign)]}
        # The other tenant's asset is untouched: no promotion, no leak.
        assert _asset_status(migrated_engine, foreign)[0] == "pending"
        assert _version_rows(migrated_engine, business) == []

    def test_an_expired_pending_logo_is_invalid_state(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """The established 409 from the shared ``claim_for_attachment``
        path (ADR-017 lifecycle), reached through the theme."""
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        expired = _insert_media_asset(migrated_engine, business, expires_hours=-1)

        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db, _actor(owner_id), business, DraftPut(config=_config(logo=expired))
            )
        db.rollback()

        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "invalid_state"
        assert _asset_status(migrated_engine, expired)[0] == "pending"
        assert _version_rows(migrated_engine, business) == []

    def test_an_exact_noop_save_reclaims_no_logo(
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
        logo = _insert_media_asset(migrated_engine, business)
        actor = _actor(owner_id)
        config = _config(logo=logo)
        storefront_service.put_draft(db, actor, business, DraftPut(config=config))
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE media_assets SET status = 'pending',"
                    " pending_expires_at = now() + interval '48 hours' WHERE id = :id"
                ),
                {"id": logo},
            )

        storefront_service.put_draft(
            db, actor, business, DraftPut(config=config, expected_lock_version=0)
        )

        assert _asset_status(migrated_engine, logo)[0] == "pending"


class TestPreM4gConfigurationCompatibility:
    """What happens to configurations written before the theme extension."""

    @staticmethod
    def _rewrite_draft_config(engine: Engine, business_id: uuid.UUID, config: str) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE storefront_versions SET config = CAST(:config AS jsonb)"
                    " WHERE business_id = :bid AND state = 'draft'"
                ),
                {"bid": business_id, "config": config},
            )

    def test_a_stored_pre_m4g_draft_reads_as_the_registry_defaults(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """No migration and no backfill: the row is read, not rewritten."""
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))
        self._rewrite_draft_config(
            migrated_engine,
            business,
            '{"schema_version": 1, "theme": {"accent": "#123abc"}, "sections": []}',
        )
        db.expire_all()

        overview = storefront_service.get_overview(db, actor, business)

        assert overview.draft is not None
        assert overview.draft.config.theme.accent == "#123abc"
        assert overview.draft.config.theme.palette.value == "warm"
        assert overview.draft.config.theme.type_pairing.value == "humanist"
        assert overview.draft.config.theme.logo is None

        # ...and the read changed nothing on disk. Defaults are supplied by
        # parsing, not by canonicalizing the row: reads never create or
        # rewrite state (ADR-020 §5.1), so the stored document is still
        # exactly the legacy shape and the concurrency token has not moved.
        # The canonical form is upgraded only by a deliberate save, which
        # the next test pins.
        stored = _version_rows(migrated_engine, business)[0]
        assert stored["config"] == {
            "schema_version": 1,
            "theme": {"accent": "#123abc"},
            "sections": [],
        }
        assert stored["lock_version"] == 0

    def test_the_first_save_of_a_pre_m4g_draft_is_not_an_exact_noop(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """A deliberate, one-off consequence, asserted rather than discovered.

        The no-op check compares the raw stored document with the fresh
        canonical dump, and the dump now carries three more theme keys. So
        the first save after M4G-A of a configuration stored before it is a
        real write: the canonical form is upgraded, ``lock_version``
        advances, and the owner sees no difference. It happens once per
        draft and changes no rendered output — every new key holds the
        default that reproduces the stored row's current appearance.
        """
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        storefront_service.put_draft(db, actor, business, DraftPut(config=_config()))
        self._rewrite_draft_config(
            migrated_engine,
            business,
            '{"schema_version": 1, "theme": {"accent": "#a34b2a"}, "sections": []}',
        )
        db.expire_all()

        view = storefront_service.put_draft(
            db, actor, business, DraftPut(config=_config(), expected_lock_version=0)
        )

        assert view.lock_version == 1
        stored = _version_rows(migrated_engine, business)[0]["config"]
        assert stored["theme"] == {
            "accent": "#a34b2a",
            "palette": "warm",
            "type_pairing": "humanist",
            "logo": None,
        }
        # And the save after that is an ordinary exact no-op again.
        again = storefront_service.put_draft(
            db, actor, business, DraftPut(config=_config(), expected_lock_version=1)
        )
        assert again.lock_version == 1


class TestThemeSnapshotStability:
    """Theme tokens travel with the version row (ADR-024 §10).

    Palette, pairing, and logo live inside the configuration, so publication
    and restore preserve them by the machinery that already exists — the
    design-variant precedent extended to the whole visual surface. No new
    lifecycle rule was needed, which is what these tests establish.
    """

    def test_publication_freezes_the_theme_into_the_published_version(
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
        logo = _insert_media_asset(migrated_engine, business)
        storefront_service.put_draft(
            db,
            actor,
            business,
            DraftPut(config=_config(logo=logo, palette="ember", type_pairing="geometric")),
        )

        storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=0))

        rows = {row["state"]: row for row in _version_rows(migrated_engine, business)}
        published_theme = rows["published"]["config"]["theme"]
        assert published_theme["palette"] == "ember"
        assert published_theme["type_pairing"] == "geometric"
        assert published_theme["logo"] == {"media_id": str(logo)}
        # Publication seeds the next draft from the published result, so the
        # owner keeps editing the same theme rather than a reset one.
        assert rows["draft"]["config"]["theme"] == published_theme

    def test_an_archived_version_keeps_the_theme_it_was_published_with(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """Changing the draft's theme and republishing must not rewrite how
        an earlier version looked."""
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        actor = _actor(owner_id)
        storefront_service.put_draft(db, actor, business, DraftPut(config=_config(palette="slate")))
        storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=0))
        storefront_service.put_draft(
            db,
            actor,
            business,
            DraftPut(config=_config(palette="midnight"), expected_lock_version=0),
        )
        storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=1))

        rows = {row["version_number"]: row for row in _version_rows(migrated_engine, business)}
        assert rows[1]["state"] == "archived"
        assert rows[1]["config"]["theme"]["palette"] == "slate"
        assert rows[2]["config"]["theme"]["palette"] == "midnight"

    def test_restore_copies_the_archived_theme_into_the_draft(
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
        logo = _insert_media_asset(migrated_engine, business)
        storefront_service.put_draft(
            db, actor, business, DraftPut(config=_config(logo=logo, palette="olive"))
        )
        storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=0))
        storefront_service.put_draft(
            db,
            actor,
            business,
            DraftPut(config=_config(palette="midnight"), expected_lock_version=0),
        )
        storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=1))
        v1_id = _version_row_id(migrated_engine, business, 1)

        view = storefront_service.restore_version(
            db, actor, business, v1_id, RestoreRequest(expected_lock_version=0)
        )

        assert view.config.theme.palette.value == "olive"
        assert view.config.theme.logo is not None
        assert view.config.theme.logo.media_id == logo


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


def _audit_events(engine: Engine, business_id: uuid.UUID, action: str) -> list[dict[str, Any]]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                "SELECT action, actor_user_id, target_type, target_id, details"
                " FROM audit_events WHERE business_id = :bid AND action = :action"
                " ORDER BY id"
            ),
            {"bid": business_id, "action": action},
        ).mappings()
        return [dict(row) for row in rows]


def _draft_row_id(engine: Engine, business_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(  # type: ignore[no-any-return]
            text("SELECT id FROM storefront_versions WHERE business_id = :bid AND state = 'draft'"),
            {"bid": business_id},
        ).scalar_one()


def _seed_owner_with_draft(
    db: Session,
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
    *,
    sections: list[dict[str, Any]] | None = None,
) -> tuple[uuid.UUID, ActorContext]:
    business = create_business()
    owner_id = create_user(OWNER)
    create_membership(business, owner_id)
    actor = _actor(owner_id)
    storefront_service.put_draft(db, actor, business, DraftPut(config=_config(sections)))
    return business, actor


class TestPublication:
    def test_first_publish_promotes_and_seeds(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership, sections=[_hero()]
        )

        overview = storefront_service.publish(
            db, actor, business, PublishRequest(expected_lock_version=0)
        )

        assert overview.published is not None
        assert overview.published.version_number == 1
        assert overview.published.published_by_user_id == actor.user.id
        assert overview.draft is not None
        assert overview.draft.lock_version == 0
        # The seeded draft is a copy of the published result (§4).
        assert overview.draft.source_version_id == overview.published.id
        assert overview.draft.config == _config([_hero()])
        events = _audit_events(migrated_engine, business, "storefront.published")
        assert len(events) == 1
        assert events[0]["target_id"] == str(overview.published.id)
        assert events[0]["details"] == {
            "version_number": 1,
            "design_variant": "classic",
            "schema_version": 1,
            "section_count": 1,
        }

    def test_second_publish_archives_the_previous_version(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=0))
        storefront_service.put_draft(
            db, actor, business, DraftPut(config=_config([_hero()]), expected_lock_version=0)
        )

        overview = storefront_service.publish(
            db, actor, business, PublishRequest(expected_lock_version=1)
        )

        assert overview.published is not None
        assert overview.published.version_number == 2
        states = {
            (row["version_number"], row["state"])
            for row in _version_rows(migrated_engine, business)
        }
        assert (1, "archived") in states
        assert (2, "published") in states
        assert (None, "draft") in states

    def test_publish_requires_the_exact_lock_version(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        storefront_service.put_draft(
            db, actor, business, DraftPut(config=_config([_hero()]), expected_lock_version=0)
        )

        with pytest.raises(ApiError) as excinfo:
            storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=0))

        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "conflict"
        assert excinfo.value.details == {"lock_version": 1}

    def test_publish_without_a_draft_is_invalid_state(
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
            storefront_service.publish(
                db, _actor(owner_id), business, PublishRequest(expected_lock_version=0)
            )

        assert excinfo.value.code.value == "invalid_state"

    def test_publishing_an_empty_config_is_legal(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # The default draft has no sections; M4D must render it coherently
        # (ADR-020 consequences) — publication must not block it.
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )

        overview = storefront_service.publish(
            db, actor, business, PublishRequest(expected_lock_version=0)
        )

        assert overview.published is not None
        events = _audit_events(migrated_engine, business, "storefront.published")
        assert events[0]["details"]["section_count"] == 0

    def test_closed_business_cannot_publish(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'closed' WHERE id = :bid"),
                {"bid": business},
            )

        with pytest.raises(ApiError) as excinfo:
            storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=0))

        assert excinfo.value.code.value == "invalid_state"

    def test_only_owners_publish(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, _ = _seed_owner_with_draft(db, create_user, create_business, create_membership)
        manager_id = create_user(MANAGER)
        create_membership(business, manager_id, role="manager")
        staff_id = create_user(STAFF)
        create_membership(business, staff_id, role="staff")

        for member_id in (manager_id, staff_id):
            with pytest.raises(PermissionDeniedError):
                storefront_service.publish(
                    db, _actor(member_id), business, PublishRequest(expected_lock_version=0)
                )
            db.rollback()
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)
        with pytest.raises(ResourceNotFoundError):
            storefront_service.publish(
                db,
                _actor(admin_id, is_platform_admin=True),
                business,
                PublishRequest(expected_lock_version=0),
            )

    def test_publication_and_audit_are_atomic(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """A commit failure durably records neither the promotion nor the
        audit event — they land together or not at all."""
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )

        with mock.patch.object(db, "commit", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                storefront_service.publish(
                    db, actor, business, PublishRequest(expected_lock_version=0)
                )
        db.rollback()

        rows = _version_rows(migrated_engine, business)
        assert [row["state"] for row in rows] == ["draft"]
        assert _audit_events(migrated_engine, business, "storefront.published") == []


def _published_row_id(engine: Engine, business_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(  # type: ignore[no-any-return]
            text(
                "SELECT id FROM storefront_versions"
                " WHERE business_id = :bid AND state = 'published'"
            ),
            {"bid": business_id},
        ).scalar_one()


def _version_row_id(engine: Engine, business_id: uuid.UUID, number: int) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(  # type: ignore[no-any-return]
            text(
                "SELECT id FROM storefront_versions"
                " WHERE business_id = :bid AND version_number = :number"
            ),
            {"bid": business_id, "number": number},
        ).scalar_one()


def _publish_two_versions(
    db: Session, business: uuid.UUID, actor: ActorContext
) -> tuple[uuid.UUID, uuid.UUID]:
    """v1 (empty) then v2 (hero); returns (v1_id, v2_id); v1 is archived."""
    storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=0))
    storefront_service.put_draft(
        db, actor, business, DraftPut(config=_config([_hero()]), expected_lock_version=0)
    )
    storefront_service.publish(db, actor, business, PublishRequest(expected_lock_version=1))
    engine = db.get_bind()
    assert isinstance(engine, Engine)
    return _version_row_id(engine, business, 1), _version_row_id(engine, business, 2)


class TestRestore:
    def test_restore_copies_config_variant_and_provenance(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        v1_id, _ = _publish_two_versions(db, business, actor)

        view = storefront_service.restore_version(
            db, actor, business, v1_id, RestoreRequest(expected_lock_version=0)
        )

        assert view.config.sections == []  # v1 was the empty config
        assert view.source_version_id == v1_id
        assert view.lock_version == 1
        events = _audit_events(migrated_engine, business, "storefront.version_restored")
        assert len(events) == 1
        assert events[0]["target_id"] == str(v1_id)
        assert events[0]["details"] == {
            "restored_from_version_number": 1,
            "design_variant": "classic",
        }
        # The source is history and history is never mutated.
        rows = {row["version_number"]: row for row in _version_rows(migrated_engine, business)}
        assert rows[1]["state"] == "archived"

    def test_restore_never_publishes(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        v1_id, v2_id = _publish_two_versions(db, business, actor)

        storefront_service.restore_version(
            db, actor, business, v1_id, RestoreRequest(expected_lock_version=0)
        )

        assert _published_row_id(migrated_engine, business) == v2_id

    def test_restore_accepts_archived_sources_only(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        _publish_two_versions(db, business, actor)
        published_id = _published_row_id(migrated_engine, business)
        draft_id = _draft_row_id(migrated_engine, business)

        # The current published row and the draft itself both exist in this
        # business but are not archived: 409 invalid_state (the ruling).
        for source_id in (published_id, draft_id):
            with pytest.raises(ApiError) as excinfo:
                storefront_service.restore_version(
                    db, actor, business, source_id, RestoreRequest(expected_lock_version=0)
                )
            assert excinfo.value.code.value == "invalid_state"
            db.rollback()

    def test_unknown_and_foreign_sources_are_the_same_404(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        other_business = create_business(slug="other-kitchen", name="Other Kitchen")
        other_owner = create_user(INTRUDER)
        create_membership(other_business, other_owner)
        other_actor = _actor(other_owner)
        storefront_service.put_draft(db, other_actor, other_business, DraftPut(config=_config()))
        foreign_v1, _ = _publish_two_versions(db, other_business, other_actor)

        with pytest.raises(ResourceNotFoundError) as foreign_exc:
            storefront_service.restore_version(
                db, actor, business, foreign_v1, RestoreRequest(expected_lock_version=0)
            )
        db.rollback()
        with pytest.raises(ResourceNotFoundError) as unknown_exc:
            storefront_service.restore_version(
                db, actor, business, uuid.uuid4(), RestoreRequest(expected_lock_version=0)
            )
        db.rollback()

        assert foreign_exc.value.message == unknown_exc.value.message

    def test_restore_without_a_draft_is_invalid_state(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # Unreachable through the API (publish always seeds a draft);
        # enforced defensively against direct manipulation.
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        v1_id, _ = _publish_two_versions(db, business, actor)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM storefront_versions WHERE business_id = :bid AND state = 'draft'"
                ),
                {"bid": business},
            )

        with pytest.raises(ApiError) as excinfo:
            storefront_service.restore_version(
                db, actor, business, v1_id, RestoreRequest(expected_lock_version=0)
            )

        assert excinfo.value.code.value == "invalid_state"

    def test_restore_requires_the_exact_lock_version(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        v1_id, _ = _publish_two_versions(db, business, actor)

        with pytest.raises(ApiError) as excinfo:
            storefront_service.restore_version(
                db, actor, business, v1_id, RestoreRequest(expected_lock_version=7)
            )

        assert excinfo.value.status_code == 409
        assert excinfo.value.code.value == "conflict"
        assert excinfo.value.details == {"lock_version": 0}

    def test_closed_lifecycle_gate_precedes_source_resolution(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'closed' WHERE id = :bid"),
                {"bid": business},
            )

        # An unknown source under a closed business: the preamble's 409
        # comes first (addendum ordering row 4 before row 5).
        with pytest.raises(ApiError) as excinfo:
            storefront_service.restore_version(
                db, actor, business, uuid.uuid4(), RestoreRequest(expected_lock_version=0)
            )

        assert excinfo.value.code.value == "invalid_state"

    def test_repeated_restore_is_effective_every_time(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # Approved completion 2: a repeated restore still increments the
        # lock, keeps provenance, and emits a new audit event.
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        v1_id, _ = _publish_two_versions(db, business, actor)
        storefront_service.restore_version(
            db, actor, business, v1_id, RestoreRequest(expected_lock_version=0)
        )

        view = storefront_service.restore_version(
            db, actor, business, v1_id, RestoreRequest(expected_lock_version=1)
        )

        assert view.lock_version == 2
        assert view.source_version_id == v1_id
        events = _audit_events(migrated_engine, business, "storefront.version_restored")
        assert len(events) == 2

    def test_corrupt_source_fails_closed_without_mutation(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # Approved completion 1: stored data the registry no longer accepts
        # propagates to the opaque internal boundary; the draft and the
        # audit stream stay untouched.
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        v1_id, _ = _publish_two_versions(db, business, actor)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE storefront_versions SET config = '{\"weird\": true}'::jsonb"
                    " WHERE id = :vid"
                ),
                {"vid": v1_id},
            )
        before = _draft_updated_at(migrated_engine, business)

        with pytest.raises(ValidationError):
            storefront_service.restore_version(
                db, actor, business, v1_id, RestoreRequest(expected_lock_version=0)
            )
        db.rollback()

        assert _draft_updated_at(migrated_engine, business) == before
        assert _audit_events(migrated_engine, business, "storefront.version_restored") == []

    def test_publish_after_restore_mints_the_next_number(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        v1_id, _ = _publish_two_versions(db, business, actor)
        storefront_service.restore_version(
            db, actor, business, v1_id, RestoreRequest(expected_lock_version=0)
        )

        overview = storefront_service.publish(
            db, actor, business, PublishRequest(expected_lock_version=1)
        )

        assert overview.published is not None
        assert overview.published.version_number == 3


class TestHistoryReads:
    def test_history_is_published_plus_archived_newest_first(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        _publish_two_versions(db, business, actor)

        page = storefront_service.list_versions(db, actor, business, limit=50, offset=0)

        assert page.total == 2
        assert [(item.version_number, item.state) for item in page.items] == [
            (2, "published"),
            (1, "archived"),
        ]

    def test_history_paginates(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        _publish_two_versions(db, business, actor)

        first = storefront_service.list_versions(db, actor, business, limit=1, offset=0)
        second = storefront_service.list_versions(db, actor, business, limit=1, offset=1)

        assert [item.version_number for item in first.items] == [2]
        assert [item.version_number for item in second.items] == [1]
        assert first.total == second.total == 2

    def test_version_detail_returns_the_composition(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        _, v2_id = _publish_two_versions(db, business, actor)

        detail = storefront_service.get_version_detail(db, actor, business, v2_id)

        assert detail.state == "published"
        assert [section.type.value for section in detail.config.sections] == ["hero"]

    def test_version_detail_never_exposes_the_draft(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        _publish_two_versions(db, business, actor)
        draft_id = _draft_row_id(migrated_engine, business)

        # The draft is not a history row: its id here is the same 404 as an
        # unknown or foreign id. The overview is the draft's only surface.
        for version_id in (draft_id, uuid.uuid4()):
            with pytest.raises(ResourceNotFoundError):
                storefront_service.get_version_detail(db, actor, business, version_id)
            db.rollback()

    def test_history_is_tenant_scoped(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        other_business = create_business(slug="other-kitchen", name="Other Kitchen")
        other_owner = create_user(INTRUDER)
        create_membership(other_business, other_owner)
        other_actor = _actor(other_owner)
        storefront_service.put_draft(db, other_actor, other_business, DraftPut(config=_config()))
        foreign_v1, _ = _publish_two_versions(db, other_business, other_actor)

        page = storefront_service.list_versions(db, actor, business, limit=50, offset=0)
        assert page.total == 0
        with pytest.raises(ResourceNotFoundError):
            storefront_service.get_version_detail(db, actor, business, foreign_v1)

    def test_history_requires_the_storefront_read_capability(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        _publish_two_versions(db, business, actor)
        staff_id = create_user(STAFF)
        create_membership(business, staff_id, role="staff")

        with pytest.raises(PermissionDeniedError):
            storefront_service.list_versions(db, _actor(staff_id), business, limit=50, offset=0)


class TestDesignAssignment:
    def test_creates_the_first_draft_with_the_requested_variant(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)

        result = storefront_service.assign_design(
            db,
            _actor(admin_id, is_platform_admin=True),
            business,
            DesignAssignment(design_variant=DesignVariant.CLASSIC),
        )

        assert result.design_variant is DesignVariant.CLASSIC
        assert result.previous_variant is None
        rows = _version_rows(migrated_engine, business)
        assert len(rows) == 1
        assert rows[0]["state"] == "draft"
        assert rows[0]["design_variant"] == "classic"
        assert rows[0]["lock_version"] == 0
        assert rows[0]["config"]["sections"] == []  # the registry default
        events = _audit_events(migrated_engine, business, "storefront.design_assigned")
        assert len(events) == 1
        # previous_variant is ABSENT from the stored payload on creation
        # (the omit-None rule) — null ⇔ first-draft creation, no boolean.
        assert events[0]["details"] == {"new_variant": "classic"}

    def test_reassigning_the_current_variant_is_an_exact_noop(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, _ = _seed_owner_with_draft(db, create_user, create_business, create_membership)
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)
        before = _draft_updated_at(migrated_engine, business)

        result = storefront_service.assign_design(
            db,
            _actor(admin_id, is_platform_admin=True),
            business,
            DesignAssignment(design_variant=DesignVariant.CLASSIC),
        )

        assert result.previous_variant is DesignVariant.CLASSIC
        assert _draft_updated_at(migrated_engine, business) == before
        rows = _version_rows(migrated_engine, business)
        assert rows[0]["lock_version"] == 0
        assert _audit_events(migrated_engine, business, "storefront.design_assigned") == []

    def test_closed_lifecycle_precedes_noop_suppression(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # §6: a design request against a closed business is 409 even when
        # the requested variant is the already-selected (no-op) value —
        # and the creation path is equally gated.
        business, _ = _seed_owner_with_draft(db, create_user, create_business, create_membership)
        closed_empty = create_business(slug="closed-empty", name="Closed Empty", status="closed")
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'closed' WHERE id = :bid"),
                {"bid": business},
            )
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)
        admin = _actor(admin_id, is_platform_admin=True)

        for target in (business, closed_empty):
            with pytest.raises(ApiError) as excinfo:
                storefront_service.assign_design(
                    db, admin, target, DesignAssignment(design_variant=DesignVariant.CLASSIC)
                )
            assert excinfo.value.code.value == "invalid_state"
            db.rollback()
        assert _audit_events(migrated_engine, business, "storefront.design_assigned") == []

    def test_members_cannot_assign_and_unknown_business_is_404(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)

        # Platform authority never comes from a membership (ADR-011): the
        # owner is denied 403 by the pure platform-capability gate.
        with pytest.raises(PermissionDeniedError):
            storefront_service.assign_design(
                db,
                _actor(owner_id),
                business,
                DesignAssignment(design_variant=DesignVariant.CLASSIC),
            )
        db.rollback()
        # Platform routes disclose existence only after the capability
        # passes: an unknown business is then a 404.
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)
        with pytest.raises(ResourceNotFoundError):
            storefront_service.assign_design(
                db,
                _actor(admin_id, is_platform_admin=True),
                uuid.uuid4(),
                DesignAssignment(design_variant=DesignVariant.CLASSIC),
            )

    def test_future_variant_assignment_increments_and_fails_stale_owner_writes(
        self,
        db: Session,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # The M4D+ seam (§6): an effective assignment increments the
        # draft's lock_version, so an owner submission based on the
        # previous version fails safely instead of silently reverting the
        # platform's assignment.
        business, actor = _seed_owner_with_draft(
            db, create_user, create_business, create_membership
        )
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)
        # M4G-B registered the second and third variants, so this runs
        # against the real enum through the ordinary request schema - no
        # model_construct bypass and no stubbed response model.
        payload = DesignAssignment(design_variant=DesignVariant.EDITORIAL)

        result = storefront_service.assign_design(
            db, _actor(admin_id, is_platform_admin=True), business, payload
        )

        assert result.previous_variant is DesignVariant.CLASSIC
        assert result.design_variant is DesignVariant.EDITORIAL
        rows = _version_rows(migrated_engine, business)
        assert rows[0]["design_variant"] == "editorial"
        assert rows[0]["lock_version"] == 1
        events = _audit_events(migrated_engine, business, "storefront.design_assigned")
        assert events[-1]["details"] == {
            "previous_variant": "classic",
            "new_variant": "editorial",
        }
        # The owner's stale write (lock 0) now conflicts (§6).
        with pytest.raises(ApiError) as excinfo:
            storefront_service.put_draft(
                db, actor, business, DraftPut(config=_config([_hero()]), expected_lock_version=0)
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.details == {"lock_version": 1}

    def test_creation_race_with_an_owner_serializes_on_the_business_lock(
        self,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """§5.8/§5.9: the platform creation path takes the same Business
        lock, so whichever command runs second operates against the
        now-existing draft according to its own contract — here, the
        assignment of the already-selected variant becomes a no-op."""
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        admin_id = create_user(PLATFORM_ADMIN, is_platform_admin=True)
        admin = _actor(admin_id, is_platform_admin=True)
        session_factory = sessionmaker(bind=migrated_engine)
        session_a = session_factory()
        outcome: dict[str, Any] = {}
        b_started = threading.Event()

        def run_b() -> None:
            session_b = session_factory()
            try:
                b_started.set()
                result = storefront_service.assign_design(
                    session_b,
                    admin,
                    business,
                    DesignAssignment(design_variant=DesignVariant.CLASSIC),
                )
                outcome["result"] = (
                    result.previous_variant.value if result.previous_variant is not None else None
                )
            except Exception as exc:  # pragma: no cover - diagnostic only
                outcome["result"] = ("unexpected", type(exc).__name__)
            finally:
                session_b.rollback()
                session_b.close()

        thread = threading.Thread(target=run_b)
        try:
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

        # B found the owner's draft already there: a no-op against it,
        # never a second draft and never an overwrite.
        assert outcome["result"] == "classic"
        rows = _version_rows(migrated_engine, business)
        assert len(rows) == 1
        assert _audit_events(migrated_engine, business, "storefront.design_assigned") == []


# --- HTTP surface (the routers over the same service rules) ------------------


CONFIG_JSON: dict[str, Any] = {
    "schema_version": 1,
    "theme": {"accent": "#a34b2a"},
    "sections": [],
}
HERO_CONFIG_JSON: dict[str, Any] = {
    "schema_version": 1,
    "theme": {"accent": "#a34b2a"},
    "sections": [{"id": "hero-main", "type": "hero", "enabled": True, "props": {"heading": "Hi"}}],
}


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/storefront"


def _error(response: Any) -> dict[str, Any]:
    return dict(response.json()["error"])


class TestHttpSurface:
    def test_anonymous_requests_are_rejected(
        self, client: Any, create_business: CreateBusiness
    ) -> None:
        business = create_business()
        assert client.get(_base(business)).status_code == 401
        assert client.get(f"{_base(business)}/versions").status_code == 401
        assert client.get(f"{_base(business)}/versions/{uuid.uuid4()}").status_code == 401
        assert (
            client.put(f"{_base(business)}/draft", json={"config": CONFIG_JSON}).status_code == 401
        )
        assert (
            client.post(f"{_base(business)}/publish", json={"expected_lock_version": 0}).status_code
            == 401
        )
        assert (
            client.post(
                f"{_base(business)}/versions/{uuid.uuid4()}/restore",
                json={"expected_lock_version": 0},
            ).status_code
            == 401
        )
        assert (
            client.put(
                f"/api/v1/platform/businesses/{business}/design",
                json={"design_variant": "classic"},
            ).status_code
            == 401
        )

    def test_unsafe_routes_require_the_csrf_token(
        self,
        client: Any,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        login_as(client, OWNER)

        # Authenticated, trusted browser context, but no synchronizer token.
        response = client.put(
            f"{_base(business)}/draft", json={"config": CONFIG_JSON}, headers=BROWSER_HEADERS
        )
        assert response.status_code == 403
        assert _error(response)["code"] == "csrf_rejected"

    def test_owner_journey_over_http(
        self,
        client: Any,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        headers = csrf_headers(csrf)

        # First-use absence.
        overview = client.get(_base(business))
        assert overview.status_code == 200
        assert overview.json() == {"draft": None, "published": None}

        # Create the draft (create intent: no expected_lock_version).
        created = client.put(
            f"{_base(business)}/draft", json={"config": HERO_CONFIG_JSON}, headers=headers
        )
        assert created.status_code == 200, created.text
        assert created.json()["lock_version"] == 0
        assert created.json()["design_variant"] == "classic"
        assert created.json()["config"]["sections"][0]["type"] == "hero"

        # Publish v1.
        published = client.post(
            f"{_base(business)}/publish", json={"expected_lock_version": 0}, headers=headers
        )
        assert published.status_code == 200, published.text
        body = published.json()
        assert body["published"]["version_number"] == 1
        assert body["draft"]["lock_version"] == 0
        assert body["draft"]["source_version_id"] == body["published"]["id"]

        # Edit and publish v2, then restore v1.
        updated = client.put(
            f"{_base(business)}/draft",
            json={"config": CONFIG_JSON, "expected_lock_version": 0},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        second = client.post(
            f"{_base(business)}/publish", json={"expected_lock_version": 1}, headers=headers
        )
        assert second.status_code == 200, second.text
        assert second.json()["published"]["version_number"] == 2

        versions = client.get(f"{_base(business)}/versions")
        assert versions.status_code == 200
        page = versions.json()
        assert page["total"] == 2
        assert [(item["version_number"], item["state"]) for item in page["items"]] == [
            (2, "published"),
            (1, "archived"),
        ]

        v1 = page["items"][1]
        detail = client.get(f"{_base(business)}/versions/{v1['id']}")
        assert detail.status_code == 200
        assert detail.json()["config"]["sections"][0]["props"]["heading"] == "Hi"

        restored = client.post(
            f"{_base(business)}/versions/{v1['id']}/restore",
            json={"expected_lock_version": 0},
            headers=headers,
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["lock_version"] == 1
        assert restored.json()["source_version_id"] == v1["id"]

        # Draft edits are never audited; publish and restore are.
        with migrated_engine.begin() as connection:
            actions = [
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT action FROM audit_events"
                        " WHERE business_id = :bid AND action LIKE 'storefront.%'"
                        " ORDER BY id"
                    ),
                    {"bid": business},
                )
            ]
        assert actions == [
            "storefront.published",
            "storefront.published",
            "storefront.version_restored",
        ]

    def test_design_variant_in_the_draft_payload_is_422(
        self,
        client: Any,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)

        response = client.put(
            f"{_base(business)}/draft",
            json={"config": CONFIG_JSON, "design_variant": "classic"},
            headers=csrf_headers(csrf),
        )

        assert response.status_code == 422
        error = _error(response)
        assert error["code"] == "validation_error"
        assert any(
            field["field"].endswith("design_variant") and field["code"] == "extra_forbidden"
            for field in error["field_errors"]
        )

    def test_stale_lock_conflict_carries_the_current_value(
        self,
        client: Any,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        headers = csrf_headers(csrf)
        client.put(f"{_base(business)}/draft", json={"config": CONFIG_JSON}, headers=headers)
        client.put(
            f"{_base(business)}/draft",
            json={"config": HERO_CONFIG_JSON, "expected_lock_version": 0},
            headers=headers,
        )

        stale = client.put(
            f"{_base(business)}/draft",
            json={"config": CONFIG_JSON, "expected_lock_version": 0},
            headers=headers,
        )

        assert stale.status_code == 409
        error = _error(stale)
        assert error["code"] == "conflict"
        assert error["details"] == {"lock_version": 1}

    def test_unknown_media_reference_envelope(
        self,
        client: Any,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        missing = str(uuid.uuid4())
        config = {
            "schema_version": 1,
            "theme": {"accent": "#a34b2a"},
            "sections": [
                {
                    "id": "hero-main",
                    "type": "hero",
                    "enabled": True,
                    "props": {"heading": "Hi", "image": {"media_id": missing}},
                }
            ],
        }

        response = client.put(
            f"{_base(business)}/draft", json={"config": config}, headers=csrf_headers(csrf)
        )

        assert response.status_code == 422
        error = _error(response)
        assert error["code"] == "validation_error"
        assert error["details"] == {"media_ids": [missing]}

    def test_corrupt_restore_source_is_an_opaque_500(
        self,
        app: Any,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # Approved completion 1 at the HTTP boundary: the fail-closed
        # rejection renders as the opaque internal_error envelope — no new
        # public error code, and no stored content in the response. A
        # non-raising client is required to observe the rendered 500.
        business = create_business()
        create_membership(business, create_user(OWNER))
        client = TestClient(app, raise_server_exceptions=False)
        csrf = login_as(client, OWNER)
        headers = csrf_headers(csrf)
        client.put(f"{_base(business)}/draft", json={"config": HERO_CONFIG_JSON}, headers=headers)
        client.post(
            f"{_base(business)}/publish", json={"expected_lock_version": 0}, headers=headers
        )
        client.put(
            f"{_base(business)}/draft",
            json={"config": CONFIG_JSON, "expected_lock_version": 0},
            headers=headers,
        )
        client.post(
            f"{_base(business)}/publish", json={"expected_lock_version": 1}, headers=headers
        )
        v1_id = _version_row_id(migrated_engine, business, 1)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE storefront_versions SET config = '{\"weird\": true}'::jsonb"
                    " WHERE id = :vid"
                ),
                {"vid": v1_id},
            )

        response = client.post(
            f"{_base(business)}/versions/{v1_id}/restore",
            json={"expected_lock_version": 0},
            headers=headers,
        )

        assert response.status_code == 500
        error = _error(response)
        assert error["code"] == "internal_error"
        assert "weird" not in response.text


class TestHttpAuthorizationMatrix:
    def test_member_role_matrix(
        self,
        client: Any,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        create_membership(business, create_user(MANAGER), role="manager")
        create_membership(business, create_user(STAFF), role="staff")
        owner_csrf = login_as(client, OWNER)
        client.put(
            f"{_base(business)}/draft",
            json={"config": CONFIG_JSON},
            headers=csrf_headers(owner_csrf),
        )

        # Staff: 403 on every storefront surface, reads included (§7).
        staff_csrf = login_as(client, STAFF)
        assert client.get(_base(business)).status_code == 403
        assert client.get(f"{_base(business)}/versions").status_code == 403
        response = client.put(
            f"{_base(business)}/draft",
            json={"config": CONFIG_JSON, "expected_lock_version": 0},
            headers=csrf_headers(staff_csrf),
        )
        assert response.status_code == 403
        assert _error(response)["code"] == "permission_denied"

        # Manager: read and write, but never publish or restore.
        manager_csrf = login_as(client, MANAGER)
        assert client.get(_base(business)).status_code == 200
        publish = client.post(
            f"{_base(business)}/publish",
            json={"expected_lock_version": 0},
            headers=csrf_headers(manager_csrf),
        )
        assert publish.status_code == 403
        restore = client.post(
            f"{_base(business)}/versions/{uuid.uuid4()}/restore",
            json={"expected_lock_version": 0},
            headers=csrf_headers(manager_csrf),
        )
        assert restore.status_code == 403

    def test_nonmembers_and_platform_admins_get_404(
        self,
        client: Any,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        other_business = create_business(slug="other-kitchen", name="Other Kitchen")
        create_membership(other_business, create_user(INTRUDER))
        create_user(PLATFORM_ADMIN, is_platform_admin=True)

        for email in (INTRUDER, PLATFORM_ADMIN):
            csrf = login_as(client, email)
            assert client.get(_base(business)).status_code == 404
            assert client.get(f"{_base(business)}/versions").status_code == 404
            response = client.put(
                f"{_base(business)}/draft",
                json={"config": CONFIG_JSON},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 404
            assert _error(response)["code"] == "not_found"

    def test_cross_tenant_version_ids_do_not_disclose(
        self,
        client: Any,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        other_business = create_business(slug="other-kitchen", name="Other Kitchen")
        create_membership(other_business, create_user(INTRUDER))
        intruder_csrf = login_as(client, INTRUDER)
        headers = csrf_headers(intruder_csrf)
        client.put(
            f"/api/v1/businesses/{other_business}/storefront/draft",
            json={"config": CONFIG_JSON},
            headers=headers,
        )
        client.post(
            f"/api/v1/businesses/{other_business}/storefront/publish",
            json={"expected_lock_version": 0},
            headers=headers,
        )

        # The owner of business A probes B's real version id under A: the
        # tenant-scoped lookup renders it exactly like a nonexistent one.
        owner_csrf = login_as(client, OWNER)
        client.put(
            f"{_base(business)}/draft",
            json={"config": CONFIG_JSON},
            headers=csrf_headers(owner_csrf),
        )
        foreign_id = _published_row_id(migrated_engine, other_business)
        real_miss = client.get(f"{_base(business)}/versions/{foreign_id}")
        fake_miss = client.get(f"{_base(business)}/versions/{uuid.uuid4()}")
        assert real_miss.status_code == fake_miss.status_code == 404
        assert _error(real_miss)["message"] == _error(fake_miss)["message"]
        restore = client.post(
            f"{_base(business)}/versions/{foreign_id}/restore",
            json={"expected_lock_version": 0},
            headers=csrf_headers(owner_csrf),
        )
        assert restore.status_code == 404

    def test_platform_design_route_matrix(
        self,
        client: Any,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        design_path = f"/api/v1/platform/businesses/{business}/design"

        # An owner holds no platform capability: 403 from the pure gate.
        owner_csrf = login_as(client, OWNER)
        denied = client.put(
            design_path,
            json={"design_variant": "classic"},
            headers=csrf_headers(owner_csrf),
        )
        assert denied.status_code == 403
        assert _error(denied)["code"] == "permission_denied"

        admin_csrf = login_as(client, PLATFORM_ADMIN)
        headers = csrf_headers(admin_csrf)
        created = client.put(design_path, json={"design_variant": "classic"}, headers=headers)
        assert created.status_code == 200, created.text
        assert created.json() == {"design_variant": "classic", "previous_variant": None}

        repeated = client.put(design_path, json={"design_variant": "classic"}, headers=headers)
        assert repeated.status_code == 200
        assert repeated.json() == {"design_variant": "classic", "previous_variant": "classic"}

        unknown_business = client.put(
            f"/api/v1/platform/businesses/{uuid.uuid4()}/design",
            json={"design_variant": "classic"},
            headers=headers,
        )
        assert unknown_business.status_code == 404

        unknown_variant = client.put(
            design_path, json={"design_variant": "brutalist"}, headers=headers
        )
        assert unknown_variant.status_code == 422
