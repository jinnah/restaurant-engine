"""Public reads under concurrent administrative change (M3D, ADR-017).

M3D runs on the existing READ COMMITTED behavior with defensive assembly
rather than escalating transaction isolation. That trade is only
acceptable if a commit landing *between* the projection's statements can
make a response briefly stale but never structurally invalid.

These tests force exactly that interleaving by patching one repository
call to mutate the database just before it reads, which is deterministic
where racing two real clients would not be. Each asserts the same
property: a valid response, no dangling reference, and no 500.

Also covers the operational failure modes of public media delivery that
are not ordinary misses.
"""

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.domains.catalog import repository
from app.domains.media import public_service as media_public
from tests.security.conftest import CreateBusiness
from tests.security.test_public_media import _publishable, _seed_asset, _url
from tests.security.test_public_menu import (
    _attach_image,
    _seed_category,
    _seed_group,
    _seed_item,
    _seed_media,
)

_MENU = "/api/v1/public/menu"


def _host(host: str = "shalik.localhost") -> dict[str, str]:
    return {"host": host}


class TestProjectionUnderConcurrentEdits:
    def test_group_deleted_between_reads_leaves_a_valid_menu(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        group_id = _seed_group(migrated_engine, business_id, item_id, options=(("Mild", 0, True),))
        real = repository.list_available_options_for_groups

        def _delete_then_read(
            db: Session, *, business_id: uuid.UUID, group_ids: list[uuid.UUID]
        ) -> Any:
            # The group (and its options) vanish after the group read but
            # before the option read — the exact READ COMMITTED window.
            with migrated_engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM modifier_groups WHERE id = :gid"), {"gid": group_id}
                )
            return real(db, business_id=business_id, group_ids=group_ids)

        monkeypatch.setattr(repository, "list_available_options_for_groups", _delete_then_read)

        response = client.get(_MENU, headers=_host())
        assert response.status_code == 200
        (item,) = response.json()["categories"][0]["items"]
        # The now-optionless group is unsatisfiable, so it is omitted rather
        # than rendered as an empty picker or crashing the projection.
        assert item["modifier_groups"] == []
        assert item["is_orderable"] is True

    def test_image_deactivated_between_reads_projects_no_image(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        asset_id = _seed_media(migrated_engine, business_id)
        _attach_image(migrated_engine, item_id, asset_id, alt="Golden samosa")
        real = media_public.list_public_representations

        def _deactivate_then_read(
            db: Session, *, business_id: uuid.UUID, asset_ids: list[uuid.UUID]
        ) -> Any:
            with migrated_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE media_assets SET status = 'pending',"
                        " pending_expires_at = now() + interval '48 hours' WHERE id = :aid"
                    ),
                    {"aid": asset_id},
                )
            return real(db, business_id=business_id, asset_ids=asset_ids)

        monkeypatch.setattr(media_public, "list_public_representations", _deactivate_then_read)

        response = client.get(_MENU, headers=_host())
        assert response.status_code == 200
        (item,) = response.json()["categories"][0]["items"]
        # No URL is advertised for an asset that was not confirmed active
        # during assembly, so the storefront never renders a link that 404s.
        assert item["image"] is None
        assert str(asset_id) not in response.text

    def test_item_deleted_between_reads_leaves_no_dangling_child(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        category_id = _seed_category(migrated_engine, business_id)
        _seed_item(migrated_engine, business_id, category_id, name="Keep", position=0)
        drop = _seed_item(migrated_engine, business_id, category_id, name="Drop", position=1)
        real = repository.list_tags_for_items

        def _delete_then_read(
            db: Session, *, business_id: uuid.UUID, item_ids: list[uuid.UUID]
        ) -> Any:
            with migrated_engine.begin() as connection:
                connection.execute(text("DELETE FROM menu_items WHERE id = :iid"), {"iid": drop})
            return real(db, business_id=business_id, item_ids=item_ids)

        monkeypatch.setattr(repository, "list_tags_for_items", _delete_then_read)

        response = client.get(_MENU, headers=_host())
        assert response.status_code == 200
        names = [item["name"] for item in response.json()["categories"][0]["items"]]
        # Briefly stale (the deleted item is still listed from the earlier
        # snapshot) but structurally sound: it has no children and nothing
        # dereferenced a row that no longer exists.
        assert "Keep" in names
        assert all(isinstance(name, str) for name in names)


class TestPublicResponseHygiene:
    def test_menu_payload_carries_no_storage_detail(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        app: FastAPI,
    ) -> None:
        business_id = create_business(slug="shalik", name="Shalik", status="active")
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        _attach_image(migrated_engine, item_id, _seed_media(migrated_engine, business_id))

        payload = client.get(_MENU, headers=_host()).text
        media_root = str(Path(app.state.media_storage.root))
        assert media_root not in payload
        assert media_root.replace("\\", "/") not in payload
        # Seeded checksum sentinels and the stored filename must not appear.
        assert "a" * 64 not in payload
        assert "b" * 64 not in payload
        assert "dish.jpg" not in payload
        assert ".webp" not in payload
        assert str(business_id) not in payload


class TestPublicMediaOperationalFailures:
    def test_an_unexpected_storage_error_is_not_cacheable(
        self,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        app: FastAPI,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # stat_object absorbs the failure modes it knows about; anything
        # else surfaces as the standard 500 envelope. The cache policy must
        # still refuse to let an error be stored.
        media_root = Path(app.state.media_storage.root)
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        def _explode(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("storage backend unavailable")

        monkeypatch.setattr(media_public, "stat_object", _explode)

        # The error handler is the subject here, so the client must let the
        # application render it instead of re-raising into the test.
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(_url(asset_id), headers=_host())
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        # No internals in the message, and never cacheable.
        assert "storage backend unavailable" not in response.text
        assert response.headers["cache-control"] == "no-store"

    def test_a_second_active_asset_of_the_same_business_is_isolated_by_attachment(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        app: FastAPI,
    ) -> None:
        # Same tenant, same active status: only the attached one is public.
        media_root = Path(app.state.media_storage.root)
        business_id, _, attached = _publishable(migrated_engine, media_root, create_business)
        unattached = _seed_asset(migrated_engine, media_root, business_id)

        assert client.get(_url(attached), headers=_host()).status_code == 200
        assert client.get(_url(unattached), headers=_host()).status_code == 404
