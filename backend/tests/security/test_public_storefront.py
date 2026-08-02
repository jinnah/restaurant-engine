"""Public storefront projection, preview, and media predicate (M4C).

Extends the permanent isolation matrix (docs/04) to the public storefront
surface: only the Host selects a Business, only an active Business with a
**currently published** version has a projection, the draft is never
reachable anonymously, and the storefront branch of the public media
predicate authorizes exactly the enabled sections of the published
version (rulings R-1, R-5, R-7).

Rows are seeded with direct SQL (the docs/06 bulk-fixture precedent)
where the test is about what the public surface *shows*; the real
service drives the publication-lifecycle cases so the projection is
proven against genuine publish/restore transitions, not hand-built rows.
"""

import hashlib
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import structlog.testing
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.domains.identity.actor import ActorContext, AuthenticatedUser
from app.domains.media.storage import object_key
from app.domains.storefront import service as storefront_service
from app.domains.storefront.composition import StorefrontConfig, parse_config
from app.domains.storefront.schemas import DraftPut, PublishRequest, RestoreRequest
from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

_STOREFRONT = "/api/v1/public/storefront"

OWNER = "owner@example.com"
MANAGER = "manager@example.com"
STAFF = "staff@example.com"
INTRUDER = "intruder-owner@example.com"
PLATFORM_ADMIN = "admin@example.com"

_PAYLOAD = b"canonical-webp-bytes"
_VARIANT_PAYLOAD = b"variant-webp-bytes"


def _host(host: str = "shalik.localhost") -> dict[str, str]:
    return {"host": host}


def _get(client: TestClient, host: str = "shalik.localhost") -> Any:
    return client.get(_STOREFRONT, headers=_host(host))


def _media_url(asset_id: uuid.UUID, variant: str = "canonical") -> str:
    return f"/api/v1/public/media/{asset_id}/{variant}"


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=migrated_engine)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def tolerant_client(app: FastAPI) -> Iterator[TestClient]:
    """A client that renders 500s instead of re-raising (corrupt-row cases)."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def media_root(app: FastAPI) -> Path:
    return Path(app.state.media_storage.root)


def _actor(user_id: uuid.UUID) -> ActorContext:
    return ActorContext(
        user=AuthenticatedUser(
            id=user_id, email=OWNER, display_name="Test User", is_platform_admin=False
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


def _config_json(
    sections: list[dict[str, Any]] | None = None,
    accent: str = "#a34b2a",
    *,
    logo: uuid.UUID | None = None,
    palette: str | None = None,
    type_pairing: str | None = None,
) -> str:
    theme: dict[str, Any] = {"accent": accent}
    if logo is not None:
        theme["logo"] = {"media_id": str(logo)}
    if palette is not None:
        theme["palette"] = palette
    if type_pairing is not None:
        theme["type_pairing"] = type_pairing
    return json.dumps({"schema_version": 1, "theme": theme, "sections": sections or []})


def _hero(
    heading: str = "Welcome",
    *,
    enabled: bool = True,
    media_id: uuid.UUID | None = None,
    alt: str | None = None,
    subheading: str | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {"heading": heading}
    if subheading is not None:
        props["subheading"] = subheading
    if media_id is not None:
        image: dict[str, Any] = {"media_id": str(media_id)}
        if alt is not None:
            image["alt_text"] = alt
        props["image"] = image
    return {"id": "hero-main", "type": "hero", "enabled": enabled, "props": props}


def _story(body: str = "A family kitchen.", *, enabled: bool = True) -> dict[str, Any]:
    return {
        "id": "story-main",
        "type": "story",
        "enabled": enabled,
        "props": {"heading": "Our story", "body": body},
    }


def _menu_section(*, enabled: bool = True) -> dict[str, Any]:
    return {
        "id": "menu-main",
        "type": "menu",
        "enabled": enabled,
        "props": {"heading": "The menu", "intro": "Cooked fresh."},
    }


def _contact(*, enabled: bool = True) -> dict[str, Any]:
    return {
        "id": "contact-main",
        "type": "contact",
        "enabled": enabled,
        "props": {
            "heading": "Find us",
            "address_lines": ["12 Bailey Ave", "Buffalo, NY"],
            "phone": "(716) 555-0100",
        },
    }


def _hours(
    *,
    enabled: bool = True,
    intro: str | None = "Kitchen closes 30 minutes early.",
    show_open_now: bool = True,
) -> dict[str, Any]:
    props: dict[str, Any] = {"heading": "Opening hours", "show_open_now": show_open_now}
    if intro is not None:
        props["intro"] = intro
    return {"id": "hours-main", "type": "hours", "enabled": enabled, "props": props}


def _gallery(
    media_ids: list[uuid.UUID], *, enabled: bool = True, heading: str | None = None
) -> dict[str, Any]:
    props: dict[str, Any] = {"images": [{"media_id": str(media_id)} for media_id in media_ids]}
    if heading is not None:
        props["heading"] = heading
    return {"id": "gallery-main", "type": "gallery", "enabled": enabled, "props": props}


def _write_object(
    root: Path, business_id: uuid.UUID, asset_id: uuid.UUID, variant: str, data: bytes
) -> None:
    path = root / object_key(business_id, asset_id, variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _seed_asset(
    engine: Engine,
    business_id: uuid.UUID,
    *,
    status: str = "active",
    root: Path | None = None,
    with_variants: bool = True,
) -> uuid.UUID:
    """Seed one asset row (plus w320/w640 variants) and optional objects."""
    asset_id = uuid.uuid4()
    expiry = "now() + interval '48 hours'" if status == "pending" else "NULL"
    widths = {"w320": 320, "w640": 640}
    with engine.begin() as connection:
        connection.execute(
            text(
                # S608: expiry is one of two test-internal literals.
                "INSERT INTO media_assets (id, business_id, kind, status,"  # noqa: S608
                " pending_expires_at, original_filename, declared_content_type,"
                " source_format, width, height, byte_size, checksum_sha256)"
                f" VALUES (:id, :bid, 'image', :status, {expiry}, 'dish.jpg',"
                " 'image/jpeg', 'jpeg', 1200, 800, :bytes, :sha)"
            ),
            {
                "id": asset_id,
                "bid": business_id,
                "status": status,
                "bytes": len(_PAYLOAD),
                "sha": hashlib.sha256(_PAYLOAD).hexdigest(),
            },
        )
        if with_variants:
            for variant, width in widths.items():
                connection.execute(
                    text(
                        "INSERT INTO media_asset_variants (id, business_id, asset_id,"
                        " variant, width, height, byte_size, checksum_sha256) VALUES"
                        " (:id, :bid, :aid, :variant, :width, :height, :bytes, :sha)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "bid": business_id,
                        "aid": asset_id,
                        "variant": variant,
                        "width": width,
                        "height": int(width * 2 / 3),
                        "bytes": len(_VARIANT_PAYLOAD),
                        "sha": hashlib.sha256(_VARIANT_PAYLOAD).hexdigest(),
                    },
                )
    if root is not None:
        _write_object(root, business_id, asset_id, "canonical", _PAYLOAD)
        if with_variants:
            for variant in widths:
                _write_object(root, business_id, asset_id, variant, _VARIANT_PAYLOAD)
    return asset_id


def _seed_version(
    engine: Engine,
    business_id: uuid.UUID,
    *,
    state: str,
    config_json: str,
    version_number: int | None = None,
    design_variant: str = "classic",
    published_by: uuid.UUID | None = None,
) -> uuid.UUID:
    """Seed one storefront version row directly (fixture setup)."""
    version_id = uuid.uuid4()
    published = "now()" if state != "draft" else "NULL"
    with engine.begin() as connection:
        connection.execute(
            text(
                # S608: published is one of two test-internal literals.
                "INSERT INTO storefront_versions (id, business_id, state,"  # noqa: S608
                " version_number, schema_version, design_variant, config,"
                f" lock_version, published_at, published_by_user_id)"
                f" VALUES (:id, :bid, :state, :number, 1, :variant,"
                f" CAST(:config AS jsonb), 0, {published}, :published_by)"
            ),
            {
                "id": version_id,
                "bid": business_id,
                "state": state,
                "number": version_number,
                "variant": design_variant,
                "config": config_json,
                "published_by": published_by,
            },
        )
    return version_id


def _published_site(
    create_business: CreateBusiness,
    create_user: CreateUser,
    engine: Engine,
    *,
    slug: str = "shalik",
    sections: list[dict[str, Any]] | None = None,
    design_variant: str = "classic",
    accent: str = "#a34b2a",
    status: str = "active",
    logo: uuid.UUID | None = None,
    palette: str | None = None,
    type_pairing: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """An active Business with one published version (seeded directly)."""
    business_id = create_business(slug=slug, name="Shalik", status=status)
    publisher = create_user(f"publisher-{slug}@example.com")
    version_id = _seed_version(
        engine,
        business_id,
        state="published",
        version_number=1,
        config_json=_config_json(
            sections, accent=accent, logo=logo, palette=palette, type_pairing=type_pairing
        ),
        design_variant=design_variant,
        published_by=publisher,
    )
    return business_id, version_id


class TestPublicStorefrontShape:
    def test_published_projection_carries_exactly_the_public_facts(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            sections=[_hero("Shalik Kitchen"), _menu_section(), _contact()],
            accent="#146b5c",
        )
        response = _get(client)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"business", "design_variant", "theme", "sections"}
        assert body["business"] == {
            "name": "Shalik",
            "slug": "shalik",
            "timezone": "America/New_York",
            "currency": "USD",
        }
        assert body["design_variant"] == "classic"
        # The theme states every token; a version stored before M4G projects
        # the registry defaults, which reproduce its current appearance.
        assert body["theme"] == {
            "accent": "#146b5c",
            "palette": "warm",
            "type_pairing": "humanist",
            "logo": None,
        }
        assert [section["type"] for section in body["sections"]] == ["hero", "menu", "contact"]
        for section in body["sections"]:
            assert set(section) == {"id", "type", "props"}
        hero = body["sections"][0]["props"]
        assert set(hero) == {"heading", "subheading", "image", "primary_action"}
        assert hero == {
            "heading": "Shalik Kitchen",
            "subheading": None,
            "image": None,
            "primary_action": "none",
        }
        contact = body["sections"][2]["props"]
        assert contact["address_lines"] == ["12 Bailey Ave", "Buffalo, NY"]

    def test_stored_registry_tokens_project_verbatim(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        """Publication stability (ADR-024 §10): a published version renders
        with the tokens it was published with, the design-variant precedent
        extended to the whole visual configuration."""
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            sections=[_hero("Shalik Kitchen")],
            palette="midnight",
            type_pairing="serif_display",
        )
        theme = _get(client).json()["theme"]
        assert theme["palette"] == "midnight"
        assert theme["type_pairing"] == "serif_display"

    def test_a_published_theme_logo_resolves_to_public_url_descriptors(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Shalik Kitchen")], logo=logo),
            published_by=publisher,
        )

        projected = _get(client).json()["theme"]["logo"]

        # Intrinsic dimensions plus renditions — and deliberately no alt
        # text: the logo is decorative and the name carries the meaning.
        assert set(projected) == {"width", "height", "url", "variants"}
        assert (projected["width"], projected["height"]) == (1200, 800)
        assert projected["url"] == _media_url(logo)
        assert [variant["variant"] for variant in projected["variants"]] == ["w320", "w640"]
        assert all(
            variant["url"] == _media_url(logo, variant["variant"])
            for variant in projected["variants"]
        )

    def test_an_unresolvable_theme_logo_degrades_to_null(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        """§7: a logo that cannot render costs nothing informational — the
        business name is always present as text — so the projection omits it
        rather than advertising a URL that would answer 404."""
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            sections=[_hero("Shalik Kitchen")],
            logo=uuid.uuid4(),
        )
        body = _get(client).json()
        assert body["theme"]["logo"] is None
        assert body["business"]["name"] == "Shalik"

    def test_a_pending_theme_logo_is_never_projected_publicly(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        pending = _seed_asset(migrated_engine, business_id, status="pending", root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Shalik Kitchen")], logo=pending),
            published_by=publisher,
        )
        assert _get(client).json()["theme"]["logo"] is None

    def test_hours_section_projects_presentation_choices_and_no_schedule(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        """The M5D section over the wire (ADR-025 D5): the published
        projection carries the owner's heading, intro, and status toggle —
        and no schedule of any shape. The weekly hours, exceptions, and
        instant facts stay the availability projection's answer
        (`GET /api/v1/public/availability`), composed at render time."""
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            sections=[_hero("Shalik Kitchen"), _hours(show_open_now=False)],
        )
        body = _get(client).json()
        assert [section["type"] for section in body["sections"]] == ["hero", "hours"]
        hours = body["sections"][1]
        assert set(hours) == {"id", "type", "props"}
        assert hours["props"] == {
            "heading": "Opening hours",
            "intro": "Kitchen closes 30 minutes early.",
            "show_open_now": False,
        }

    def test_disabled_sections_are_omitted_and_order_is_preserved(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            sections=[_story("Visible story"), _hero("Hidden hero", enabled=False), _contact()],
        )
        body = _get(client).json()
        assert [section["type"] for section in body["sections"]] == ["story", "contact"]
        assert "Hidden hero" not in str(body)

    def test_empty_published_configuration_projects_coherently(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        # The default draft has no sections (ADR-020), so an owner can
        # publish an empty page; the projection must be a valid 200.
        _published_site(create_business, create_user, migrated_engine, sections=[])
        response = _get(client)
        assert response.status_code == 200
        assert response.json()["sections"] == []

    def test_active_image_resolves_to_public_url_descriptors(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Welcome", media_id=asset_id, alt="The dining room")]),
            published_by=publisher,
        )
        image = _get(client).json()["sections"][0]["props"]["image"]
        assert image["alt_text"] == "The dining room"
        assert image["width"] == 1200
        assert image["height"] == 800
        assert image["url"] == _media_url(asset_id)
        assert [variant["variant"] for variant in image["variants"]] == ["w320", "w640"]
        assert [variant["url"] for variant in image["variants"]] == [
            _media_url(asset_id, "w320"),
            _media_url(asset_id, "w640"),
        ]
        # No asset id, storage key, or checksum outside the URL itself.
        assert "checksum" not in str(image)

    def test_unknown_and_pending_references_degrade_without_dead_urls(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        pending = _seed_asset(migrated_engine, business_id, status="pending")
        active = _seed_asset(migrated_engine, business_id)
        missing = uuid.uuid4()
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json(
                [_hero("Welcome", media_id=pending), _gallery([missing, active])]
            ),
            published_by=publisher,
        )
        body = _get(client).json()
        hero, gallery = body["sections"]
        # A pending asset is never advertised publicly (ADR-017 R7).
        assert hero["props"]["image"] is None
        # The gallery degrades by omission; the resolvable image survives.
        urls = [image["url"] for image in gallery["props"]["images"]]
        assert urls == [_media_url(active)]
        assert str(pending) not in str(body)
        assert str(missing) not in str(body)

    def test_success_is_cacheable_for_sixty_seconds(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(create_business, create_user, migrated_engine)
        response = _get(client)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=60"

    def test_head_companion_matches_get(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(create_business, create_user, migrated_engine)
        response = client.head(_STOREFRONT, headers=_host())
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=60"
        assert response.content == b""

    def test_no_authentication_session_or_csrf_is_required(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(create_business, create_user, migrated_engine)
        assert client.get(_STOREFRONT, headers=_host()).status_code == 200


class TestPublicStorefrontResolution:
    def _assert_neutral_404(self, response: Any) -> None:
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Not found."
        assert response.headers["cache-control"] == "no-store"

    def test_business_with_no_storefront_rows_is_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business(slug="shalik", name="Shalik", status="active")
        self._assert_neutral_404(_get(client))

    def test_draft_only_business_is_neutral_404(
        self, client: TestClient, create_business: CreateBusiness, migrated_engine: Engine
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        _seed_version(
            migrated_engine,
            business_id,
            state="draft",
            config_json=_config_json([_hero("Draft only")]),
        )
        response = _get(client)
        self._assert_neutral_404(response)
        assert "Draft only" not in response.text

    def test_unknown_host_is_neutral_404(self, client: TestClient) -> None:
        self._assert_neutral_404(_get(client, "nope.localhost"))

    def test_non_active_states_are_neutral_404_even_with_a_published_version(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        for state in ("provisioning", "suspended", "closed"):
            _published_site(
                create_business,
                create_user,
                migrated_engine,
                slug=f"biz-{state}",
                sections=[_hero("Hidden storefront")],
                status=state,
            )
            response = _get(client, f"biz-{state}.localhost")
            self._assert_neutral_404(response)
            assert "Hidden storefront" not in response.text

    def test_malformed_reserved_apex_and_ip_hosts_are_neutral_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(create_business, create_user, migrated_engine)
        for host in ("bad_host", "api.localhost", "localhost", "a.shalik.localhost", "127.0.0.1"):
            self._assert_neutral_404(_get(client, host))

    def test_each_host_returns_only_its_own_storefront(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            slug="alpha",
            sections=[_hero("Alpha hero")],
        )
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            slug="bravo",
            sections=[_hero("Bravo hero")],
        )
        alpha = _get(client, "alpha.localhost")
        bravo = _get(client, "bravo.localhost")
        assert alpha.status_code == bravo.status_code == 200
        assert (
            alpha.headers["cache-control"]
            == bravo.headers["cache-control"]
            == ("public, max-age=60")
        )
        assert alpha.json()["sections"][0]["props"]["heading"] == "Alpha hero"
        assert bravo.json()["sections"][0]["props"]["heading"] == "Bravo hero"
        assert "Bravo" not in alpha.text
        assert "Alpha" not in bravo.text

    def test_unsafe_methods_are_not_allowed(self, client: TestClient) -> None:
        for request in (client.post, client.put, client.delete, client.patch):
            response = request(_STOREFRONT, headers=_host("shalik.localhost"))
            assert response.status_code in (400, 405)
            assert response.headers["cache-control"] == "no-store"


class TestPublicationLifecycle:
    """The projection follows real publish/restore transitions (R-1)."""

    def _owner(
        self,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> tuple[uuid.UUID, ActorContext]:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        owner_id = create_user(OWNER)
        create_membership(business_id, owner_id)
        return business_id, _actor(owner_id)

    def test_draft_edits_never_appear_before_publication(
        self,
        client: TestClient,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, actor = self._owner(db, create_user, create_business, create_membership)
        storefront_service.put_draft(
            db, actor, business_id, DraftPut(config=_config([_hero("Version one")]))
        )
        storefront_service.publish(db, actor, business_id, PublishRequest(expected_lock_version=0))
        storefront_service.put_draft(
            db,
            actor,
            business_id,
            DraftPut(config=_config([_hero("Unpublished edit")]), expected_lock_version=0),
        )
        body = _get(client).json()
        assert body["sections"][0]["props"]["heading"] == "Version one"
        assert "Unpublished edit" not in str(body)

    def test_new_publication_replaces_the_previous_projection(
        self,
        client: TestClient,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, actor = self._owner(db, create_user, create_business, create_membership)
        storefront_service.put_draft(
            db, actor, business_id, DraftPut(config=_config([_hero("Version one")]))
        )
        storefront_service.publish(db, actor, business_id, PublishRequest(expected_lock_version=0))
        storefront_service.put_draft(
            db,
            actor,
            business_id,
            DraftPut(config=_config([_hero("Version two")]), expected_lock_version=0),
        )
        storefront_service.publish(db, actor, business_id, PublishRequest(expected_lock_version=1))
        body = _get(client).json()
        assert body["sections"][0]["props"]["heading"] == "Version two"
        # The superseded (archived) content is gone from the public surface.
        assert "Version one" not in str(body)

    def test_restored_content_serves_only_after_its_own_publication(
        self,
        client: TestClient,
        db: Session,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id, actor = self._owner(db, create_user, create_business, create_membership)
        storefront_service.put_draft(
            db, actor, business_id, DraftPut(config=_config([_hero("Version one")]))
        )
        storefront_service.publish(db, actor, business_id, PublishRequest(expected_lock_version=0))
        storefront_service.put_draft(
            db,
            actor,
            business_id,
            DraftPut(config=_config([_hero("Version two")]), expected_lock_version=0),
        )
        storefront_service.publish(db, actor, business_id, PublishRequest(expected_lock_version=1))
        with migrated_engine.begin() as connection:
            archived_id = connection.execute(
                text(
                    "SELECT id FROM storefront_versions"
                    " WHERE business_id = :bid AND state = 'archived'"
                ),
                {"bid": business_id},
            ).scalar_one()
        storefront_service.restore_version(
            db, actor, business_id, archived_id, RestoreRequest(expected_lock_version=0)
        )
        # Restore mutates only the draft: the public projection still
        # serves version two until the restored draft is published.
        assert _get(client).json()["sections"][0]["props"]["heading"] == "Version two"
        storefront_service.publish(db, actor, business_id, PublishRequest(expected_lock_version=1))
        assert _get(client).json()["sections"][0]["props"]["heading"] == "Version one"


class TestCorruptPublishedState:
    """Ruling R-6: projection fails loud (opaque 500); errors stay no-store."""

    def test_corrupt_published_config_is_an_opaque_500(
        self,
        tolerant_client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json='{"schema_version": 1, "sections": [{"type": "campaign"}]}',
            published_by=publisher,
        )
        response = tolerant_client.get(_STOREFRONT, headers=_host())
        assert response.status_code == 500
        body = response.json()
        assert body["error"]["code"] == "internal_error"
        # Nothing about the stored configuration is disclosed.
        assert "campaign" not in response.text
        assert response.headers["cache-control"] == "no-store"

    def test_unregistered_stored_variant_is_an_opaque_500(
        self,
        tolerant_client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(
            create_business,
            create_user,
            migrated_engine,
            sections=[],
            design_variant="vintage",
        )
        response = tolerant_client.get(_STOREFRONT, headers=_host())
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "vintage" not in response.text
        assert response.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize(
        ("token", "palette", "type_pairing"),
        [
            ("retired-scheme", "retired-scheme", None),
            ("retired-pairing", None, "retired-pairing"),
        ],
    )
    def test_an_unregistered_stored_theme_token_is_an_opaque_500(
        self,
        token: str,
        palette: str | None,
        type_pairing: str | None,
        tolerant_client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        """The M4G-A registries fail closed exactly like the variant does.

        ADR-024 §10: a stored palette or pairing the registry no longer
        accepts is an integrity defect, and the projection must fail loud
        rather than render a guessed default — which would misrepresent a
        published version as something its owner never approved. Retiring an
        entry removes it from the *assignable* set only (renderable ⊇
        assignable), so this state is reachable only through drift or
        corruption, never through the API.

        The authorization side of the same corruption is the opposite
        answer by design (ruling R-6) and is proved separately in
        ``TestThemeLogoMediaDelivery``: the anonymous media route keeps its
        neutral 404.
        """
        business_id, _ = _published_site(
            create_business,
            create_user,
            migrated_engine,
            sections=[],
            palette=palette,
            type_pairing=type_pairing,
        )

        with structlog.testing.capture_logs() as logs:
            response = tolerant_client.get(_STOREFRONT, headers=_host())

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert response.headers["cache-control"] == "no-store"
        # The stored token never reaches the client.
        assert token not in response.text

        # ...and the bounded anomaly is recorded on the established
        # public_projection path: a reason code plus the business id, and
        # nothing of the configuration itself.
        warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
        assert [entry["event"] for entry in warnings] == ["storefront_published_config_invalid"]
        assert set(warnings[0]) == {"event", "log_level", "business_id", "context"}
        assert warnings[0]["business_id"] == str(business_id)
        assert warnings[0]["context"] == "public_projection"
        assert token not in str(warnings[0])


class TestBoundedQueries:
    """The projection must not issue work per section or per image."""

    @staticmethod
    @contextmanager
    def _statements(app: FastAPI) -> Iterator[list[str]]:
        recorded: list[str] = []

        def _before(_conn: Any, _cursor: Any, statement: str, *_rest: Any, **_kwargs: Any) -> None:
            recorded.append(statement)

        event.listen(app.state.engine, "before_cursor_execute", _before)
        try:
            yield recorded
        finally:
            event.remove(app.state.engine, "before_cursor_execute", _before)

    def test_statement_count_does_not_grow_with_sections_or_media(
        self,
        client: TestClient,
        app: FastAPI,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        small_business = create_business(slug="small", name="Small", status="active")
        small_asset = _seed_asset(migrated_engine, small_business)
        publisher = create_user("publisher-small@example.com")
        _seed_version(
            migrated_engine,
            small_business,
            state="published",
            version_number=1,
            config_json=_config_json([_gallery([small_asset])]),
            published_by=publisher,
        )
        large_business = create_business(slug="large", name="Large", status="active")
        large_assets = [_seed_asset(migrated_engine, large_business) for _ in range(6)]
        publisher_large = create_user("publisher-large@example.com")
        _seed_version(
            migrated_engine,
            large_business,
            state="published",
            version_number=1,
            config_json=_config_json(
                [
                    _hero("Large", media_id=large_assets[0]),
                    _menu_section(),
                    _story(),
                    _contact(),
                    _gallery(large_assets[1:]),
                ]
            ),
            published_by=publisher_large,
        )

        with self._statements(app) as recorded:
            assert _get(client, "small.localhost").status_code == 200
            small_count = len(recorded)
        with self._statements(app) as recorded:
            body = _get(client, "large.localhost").json()
            large_count = len(recorded)

        assert len(body["sections"]) == 5
        assert small_count == large_count
        # Host resolution, the published row, assets, and variants: a
        # fixed, bounded plan.
        assert small_count == 4

    def test_media_statements_are_skipped_when_nothing_is_referenced(
        self,
        client: TestClient,
        app: FastAPI,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        _published_site(
            create_business, create_user, migrated_engine, sections=[_story(), _contact()]
        )
        with self._statements(app) as recorded:
            assert _get(client).status_code == 200
        assert len(recorded) == 2

    def test_a_theme_logo_costs_no_additional_statement(
        self,
        client: TestClient,
        app: FastAPI,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        """The logo joins the one batched media read rather than adding its
        own: the theme leg is a wider collection, not a second query."""
        with_logo = create_business(slug="logo", name="Logo", status="active")
        logo_asset = _seed_asset(migrated_engine, with_logo)
        publisher = create_user("publisher-logo@example.com")
        _seed_version(
            migrated_engine,
            with_logo,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Home", media_id=logo_asset)], logo=logo_asset),
            published_by=publisher,
        )
        section_only = create_business(slug="plain", name="Plain", status="active")
        plain_asset = _seed_asset(migrated_engine, section_only)
        publisher_plain = create_user("publisher-plain@example.com")
        _seed_version(
            migrated_engine,
            section_only,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Home", media_id=plain_asset)]),
            published_by=publisher_plain,
        )

        with self._statements(app) as recorded:
            assert _get(client, "logo.localhost").status_code == 200
            logo_count = len(recorded)
        with self._statements(app) as recorded:
            assert _get(client, "plain.localhost").status_code == 200
            plain_count = len(recorded)

        assert logo_count == plain_count


class TestPreview:
    """The authenticated draft preview (ADR-020 §9, rulings R-4)."""

    def _workspace(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        *,
        status: str = "active",
        sections: list[dict[str, Any]] | None = None,
    ) -> tuple[uuid.UUID, str]:
        """An owner logged in, with a draft created through the real API."""
        business_id = create_business(slug="shalik", name="Shalik", status=status)
        owner_id = create_user(OWNER)
        create_membership(business_id, owner_id)
        csrf = login_as(client, OWNER)
        response = client.put(
            f"/api/v1/businesses/{business_id}/storefront/draft",
            json={
                "config": {
                    "schema_version": 1,
                    "theme": {"accent": "#a34b2a"},
                    "sections": sections if sections is not None else [_hero("Draft hero")],
                }
            },
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200, response.text
        return business_id, csrf

    def _preview(self, client: TestClient, business_id: uuid.UUID) -> Any:
        return client.get(f"/api/v1/businesses/{business_id}/storefront/preview")

    def test_owner_previews_the_draft_with_preview_headers(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = self._workspace(client, create_user, create_business, create_membership)
        response = self._preview(client, business_id)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"business", "design_variant", "theme", "sections"}
        assert body["business"]["slug"] == "shalik"
        assert body["sections"][0]["props"]["heading"] == "Draft hero"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-robots-tag"] == "noindex"

    def test_preview_is_render_equivalent_disabled_sections_are_omitted(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = self._workspace(
            client,
            create_user,
            create_business,
            create_membership,
            sections=[_hero("Kept"), _story(enabled=False)],
        )
        body = self._preview(client, business_id).json()
        assert [section["type"] for section in body["sections"]] == ["hero"]

    def test_manager_may_preview(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = self._workspace(client, create_user, create_business, create_membership)
        manager_id = create_user(MANAGER)
        create_membership(business_id, manager_id, role="manager")
        login_as(client, MANAGER)
        assert self._preview(client, business_id).status_code == 200

    def test_staff_receive_403(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = self._workspace(client, create_user, create_business, create_membership)
        staff_id = create_user(STAFF)
        create_membership(business_id, staff_id, role="staff")
        login_as(client, STAFF)
        response = self._preview(client, business_id)
        assert response.status_code == 403
        assert "Draft hero" not in response.text

    def test_cross_tenant_member_receives_the_indistinguishable_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = self._workspace(client, create_user, create_business, create_membership)
        other_business = create_business(slug="other", name="Other")
        intruder_id = create_user(INTRUDER)
        create_membership(other_business, intruder_id)
        login_as(client, INTRUDER)
        response = self._preview(client, business_id)
        assert response.status_code == 404
        assert "Draft hero" not in response.text

    def test_platform_admin_without_membership_receives_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = self._workspace(client, create_user, create_business, create_membership)
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        login_as(client, PLATFORM_ADMIN)
        assert self._preview(client, business_id).status_code == 404

    def test_unauthenticated_preview_is_401(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = self._workspace(client, create_user, create_business, create_membership)
        client.cookies.clear()
        assert self._preview(client, business_id).status_code == 401

    def test_no_draft_is_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        owner_id = create_user(OWNER)
        create_membership(business_id, owner_id)
        login_as(client, OWNER)
        assert self._preview(client, business_id).status_code == 404

    def test_provisioning_suspended_and_closed_businesses_stay_previewable(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id, _ = self._workspace(
            client, create_user, create_business, create_membership, status="provisioning"
        )
        assert self._preview(client, business_id).status_code == 200
        for status in ("suspended", "closed"):
            with migrated_engine.begin() as connection:
                connection.execute(
                    text("UPDATE businesses SET status = :status WHERE id = :bid"),
                    {"status": status, "bid": business_id},
                )
            assert self._preview(client, business_id).status_code == 200, status

    def test_pending_draft_media_uses_authenticated_urls(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        # Seeded directly: a draft referencing a still-pending asset (the
        # API claim path would have promoted it), so preview must both
        # include it and address it through the member media route.
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        owner_id = create_user(OWNER)
        create_membership(business_id, owner_id)
        pending = _seed_asset(migrated_engine, business_id, status="pending")
        _seed_version(
            migrated_engine,
            business_id,
            state="draft",
            config_json=_config_json([_hero("Draft hero", media_id=pending)]),
        )
        login_as(client, OWNER)
        image = self._preview(client, business_id).json()["sections"][0]["props"]["image"]
        assert image is not None
        assert image["url"] == (f"/api/v1/businesses/{business_id}/media/{pending}/file/canonical")
        assert all(
            variant["url"].startswith(f"/api/v1/businesses/{business_id}/media/")
            for variant in image["variants"]
        )
        # Never the anonymous delivery path for a draft asset.
        assert "/api/v1/public/media/" not in str(image)

    def test_a_pending_theme_logo_is_previewed_through_the_member_route(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        """ADR-024 §7: preview includes a pending theme logo exactly as it
        includes pending section media — the one surface that already serves
        draft assets, so no new delivery route exists."""
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        owner_id = create_user(OWNER)
        create_membership(business_id, owner_id)
        pending = _seed_asset(migrated_engine, business_id, status="pending")
        _seed_version(
            migrated_engine,
            business_id,
            state="draft",
            config_json=_config_json([_hero("Draft hero")], logo=pending),
        )
        login_as(client, OWNER)

        logo = self._preview(client, business_id).json()["theme"]["logo"]

        assert logo is not None
        assert logo["url"] == f"/api/v1/businesses/{business_id}/media/{pending}/file/canonical"
        assert all(
            variant["url"].startswith(f"/api/v1/businesses/{business_id}/media/")
            for variant in logo["variants"]
        )
        assert "/api/v1/public/media/" not in str(logo)

    def test_the_preview_theme_carries_the_draft_registry_tokens(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        owner_id = create_user(OWNER)
        create_membership(business_id, owner_id)
        _seed_version(
            migrated_engine,
            business_id,
            state="draft",
            config_json=_config_json([_hero("Draft")], palette="olive", type_pairing="geometric"),
        )
        login_as(client, OWNER)

        theme = self._preview(client, business_id).json()["theme"]

        assert theme["palette"] == "olive"
        assert theme["type_pairing"] == "geometric"
        assert theme["logo"] is None


class TestThemeLogoMediaDelivery:
    """The §10 predicate's third leg (ADR-020 amendment, ADR-024 §7).

    Same isolation discipline as its M4C predecessor: every negative case
    that authorizes nothing for a *section* reference must authorize nothing
    for a *theme* reference either, and the one genuinely new property — the
    theme leg is independent of section enablement — is proved directly.
    """

    def _delivery(
        self, client: TestClient, asset_id: uuid.UUID, host: str = "shalik.localhost"
    ) -> Any:
        return client.get(_media_url(asset_id), headers=_host(host))

    def test_a_published_theme_logo_authorizes_delivery(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Home")], logo=logo),
            published_by=publisher,
        )

        response = self._delivery(client, logo)

        assert response.status_code == 200
        assert response.content == _PAYLOAD
        assert response.headers["cache-control"] == "public, max-age=3600, immutable"

    def test_the_logo_is_authorized_with_every_section_disabled(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        """The new property: a logo is chrome, not a section. Disabling every
        section withdraws the section leg and leaves the theme leg intact —
        which is exactly why it had to be a third leg rather than a widening
        of the section rule."""
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Hidden", enabled=False)], logo=logo),
            published_by=publisher,
        )

        assert self._delivery(client, logo).status_code == 200
        # ...and the projection really does present no sections at all.
        assert _get(client).json()["sections"] == []

    def test_a_disabled_section_reference_still_authorizes_nothing(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        """The converse guard: adding the theme leg must not have loosened
        the disabled-section rule (R-5 stands unchanged)."""
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        hidden = _seed_asset(migrated_engine, business_id, root=media_root)
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Hidden", enabled=False, media_id=hidden)], logo=logo),
            published_by=publisher,
        )

        assert self._delivery(client, logo).status_code == 200
        assert self._delivery(client, hidden).status_code == 404

    def test_a_draft_only_theme_logo_authorizes_nothing(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        _seed_version(
            migrated_engine,
            business_id,
            state="draft",
            config_json=_config_json([_hero("Draft")], logo=logo),
        )
        assert self._delivery(client, logo).status_code == 404

    def test_an_archived_only_theme_logo_authorizes_nothing(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="archived",
            version_number=1,
            config_json=_config_json([_hero("Old")], logo=logo),
            published_by=publisher,
        )
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=2,
            config_json=_config_json([_hero("New")]),
            published_by=publisher,
        )
        assert self._delivery(client, logo).status_code == 404

    def test_a_logo_removed_by_a_newer_publication_authorizes_nothing(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        """§10's stated sequence: the logo stays public while the published
        version references it, and stops the moment a publication drops it."""
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        first = _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Home")], logo=logo),
            published_by=publisher,
        )
        assert self._delivery(client, logo).status_code == 200

        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE storefront_versions SET state = 'archived' WHERE id = :id"),
                {"id": first},
            )
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=2,
            config_json=_config_json([_hero("Home")]),
            published_by=publisher,
        )

        assert self._delivery(client, logo).status_code == 404

    def test_a_pending_asset_referenced_by_a_published_theme_stays_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        """Public delivery never serves pending media (ADR-017 R7); the
        theme leg grants display authorization, never inventory eligibility."""
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        pending = _seed_asset(migrated_engine, business_id, status="pending", root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Home")], logo=pending),
            published_by=publisher,
        )
        assert self._delivery(client, pending).status_code == 404

    def test_a_theme_logo_does_not_cross_businesses(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        """Tenant isolation on the new leg: each host authorizes only its own
        published theme, in the same run so neither result is incidental."""
        first_id = create_business(slug="shalik", name="Shalik", status="active")
        second_id = create_business(slug="tandoor", name="Tandoor", status="active")
        publisher = create_user("publisher@example.com")
        first_logo = _seed_asset(migrated_engine, first_id, root=media_root)
        second_logo = _seed_asset(migrated_engine, second_id, root=media_root)
        for business_id, logo in ((first_id, first_logo), (second_id, second_logo)):
            _seed_version(
                migrated_engine,
                business_id,
                state="published",
                version_number=1,
                config_json=_config_json([_hero("Home")], logo=logo),
                published_by=publisher,
            )

        assert self._delivery(client, first_logo, "shalik.localhost").status_code == 200
        assert self._delivery(client, second_logo, "tandoor.localhost").status_code == 200
        # Neither host may deliver the other's logo.
        assert self._delivery(client, second_logo, "shalik.localhost").status_code == 404
        assert self._delivery(client, first_logo, "tandoor.localhost").status_code == 404

    def test_an_unregistered_stored_palette_denies_with_the_neutral_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        """Fail-closed on the authorization side (ruling R-6): a stored token
        the registry no longer accepts is an integrity defect that authorizes
        nothing, and the anonymous route keeps its neutral 404 rather than
        surfacing a 500."""
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        logo = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        version_id = _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=_config_json([_hero("Home")], logo=logo),
            published_by=publisher,
        )
        assert self._delivery(client, logo).status_code == 200

        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE storefront_versions SET config ="
                    " jsonb_set(config, '{theme,palette}', '\"retired-scheme\"')"
                    " WHERE id = :id"
                ),
                {"id": version_id},
            )

        assert self._delivery(client, logo).status_code == 404


class TestStorefrontMediaDelivery:
    """The storefront branch of the public media predicate (R-5, R-7)."""

    def _delivery(
        self, client: TestClient, asset_id: uuid.UUID, host: str = "shalik.localhost"
    ) -> Any:
        return client.get(_media_url(asset_id), headers=_host(host))

    def _publish_reference(
        self,
        engine: Engine,
        business_id: uuid.UUID,
        publisher: uuid.UUID,
        sections: list[dict[str, Any]],
        *,
        version_number: int = 1,
    ) -> uuid.UUID:
        return _seed_version(
            engine,
            business_id,
            state="published",
            version_number=version_number,
            config_json=_config_json(sections),
            published_by=publisher,
        )

    def test_enabled_published_reference_authorizes_delivery(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        self._publish_reference(
            migrated_engine, business_id, publisher, [_hero("Home", media_id=asset_id)]
        )
        response = self._delivery(client, asset_id)
        assert response.status_code == 200
        assert response.content == _PAYLOAD
        assert response.headers["cache-control"] == "public, max-age=3600, immutable"

    def test_draft_only_reference_authorizes_nothing(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        _seed_version(
            migrated_engine,
            business_id,
            state="draft",
            config_json=_config_json([_hero("Draft", media_id=asset_id)]),
        )
        assert self._delivery(client, asset_id).status_code == 404

    def test_archived_only_reference_authorizes_nothing(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="archived",
            version_number=1,
            config_json=_config_json([_hero("Old", media_id=asset_id)]),
            published_by=publisher,
        )
        self._publish_reference(
            migrated_engine, business_id, publisher, [_hero("New")], version_number=2
        )
        assert self._delivery(client, asset_id).status_code == 404

    def test_disabled_section_reference_authorizes_nothing_until_enabled(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        """The R-5 sequence: disabled → 404; enabled + republished → 200;
        disabled again by a newer publication → 404."""
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        version_id = self._publish_reference(
            migrated_engine,
            business_id,
            publisher,
            [_hero("Home", enabled=False, media_id=asset_id)],
        )
        assert self._delivery(client, asset_id).status_code == 404

        # The same section enabled and newly published: eligibility begins.
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE storefront_versions SET state = 'archived' WHERE id = :id"),
                {"id": version_id},
            )
        self._publish_reference(
            migrated_engine,
            business_id,
            publisher,
            [_hero("Home", enabled=True, media_id=asset_id)],
            version_number=2,
        )
        assert self._delivery(client, asset_id).status_code == 200

        # Disabled again by a newer publication, no other reference: gone.
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE storefront_versions SET state = 'archived'"
                    " WHERE business_id = :bid AND state = 'published'"
                ),
                {"bid": business_id},
            )
        self._publish_reference(
            migrated_engine,
            business_id,
            publisher,
            [_hero("Home", enabled=False, media_id=asset_id)],
            version_number=3,
        )
        assert self._delivery(client, asset_id).status_code == 404

    def test_removed_by_newer_publication_authorizes_nothing(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="archived",
            version_number=1,
            config_json=_config_json([_gallery([asset_id])]),
            published_by=publisher,
        )
        self._publish_reference(
            migrated_engine, business_id, publisher, [_story()], version_number=2
        )
        assert self._delivery(client, asset_id).status_code == 404

    def test_catalog_attachment_still_authorizes_without_a_storefront(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        # Control: the M3D branch is intact when no storefront rows exist.
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        category_id = uuid.uuid4()
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (:id, :bid, 'Curries', 0, TRUE)"
                ),
                {"id": category_id, "bid": business_id},
            )
            connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured,"
                    " image_media_id) VALUES (:id, :bid, :cid, 'Samosa', 350, 0,"
                    " TRUE, FALSE, FALSE, :aid)"
                ),
                {"id": uuid.uuid4(), "bid": business_id, "cid": category_id, "aid": asset_id},
            )
        assert self._delivery(client, asset_id).status_code == 200

    def test_catalog_success_short_circuits_the_storefront_lookup(
        self,
        client: TestClient,
        app: FastAPI,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        # Referenced by BOTH: a visible menu item and the published version.
        category_id = uuid.uuid4()
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (:id, :bid, 'Curries', 0, TRUE)"
                ),
                {"id": category_id, "bid": business_id},
            )
            connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured,"
                    " image_media_id) VALUES (:id, :bid, :cid, 'Samosa', 350, 0,"
                    " TRUE, FALSE, FALSE, :aid)"
                ),
                {"id": uuid.uuid4(), "bid": business_id, "cid": category_id, "aid": asset_id},
            )
        self._publish_reference(
            migrated_engine, business_id, publisher, [_hero("Home", media_id=asset_id)]
        )

        recorded: list[str] = []

        def _before(_conn: Any, _cursor: Any, statement: str, *_rest: Any, **_kwargs: Any) -> None:
            recorded.append(statement)

        event.listen(app.state.engine, "before_cursor_execute", _before)
        try:
            assert self._delivery(client, asset_id).status_code == 200
        finally:
            event.remove(app.state.engine, "before_cursor_execute", _before)
        # The catalog predicate authorized the asset, so the published
        # storefront row was never read — the M3D hot path is unchanged.
        assert not [s for s in recorded if "storefront_versions" in s]

    def test_cross_business_isolation_in_the_same_run(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        alpha = create_business(slug="alpha", name="Alpha", status="active")
        bravo = create_business(slug="bravo", name="Bravo", status="active")
        alpha_asset = _seed_asset(migrated_engine, alpha, root=media_root)
        publisher = create_user("publisher@example.com")
        self._publish_reference(
            migrated_engine, alpha, publisher, [_hero("Alpha", media_id=alpha_asset)]
        )
        _seed_version(
            migrated_engine,
            bravo,
            state="published",
            version_number=1,
            config_json=_config_json([_story()]),
            published_by=publisher,
        )
        # A 404 for something served one host away is the boundary.
        assert self._delivery(client, alpha_asset, "alpha.localhost").status_code == 200
        assert self._delivery(client, alpha_asset, "bravo.localhost").status_code == 404

    def test_pending_asset_referenced_by_published_config_stays_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        # The media inventory half still gates: an enabled published
        # reference cannot resurrect a pending asset anonymously.
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, status="pending", root=media_root)
        publisher = create_user("publisher@example.com")
        self._publish_reference(
            migrated_engine, business_id, publisher, [_hero("Home", media_id=asset_id)]
        )
        assert self._delivery(client, asset_id).status_code == 404

    def test_corrupt_published_config_denies_with_the_neutral_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        # Ruling R-6: the authorization predicate fails closed to deny —
        # a neutral 404 on the anonymous route, never a 500, never access.
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        asset_id = _seed_asset(migrated_engine, business_id, root=media_root)
        publisher = create_user("publisher@example.com")
        _seed_version(
            migrated_engine,
            business_id,
            state="published",
            version_number=1,
            config_json=f'{{"sections": [{{"media": "{asset_id}"}}]}}',
            published_by=publisher,
        )
        response = self._delivery(client, asset_id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
