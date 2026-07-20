"""Media backend behavior, authorization, and tenant isolation (M3C, ADR-017).

Extends the permanent isolation matrix (docs/04) to media assets and
proves the service rules: the upload pipeline (pending asset + variants +
audit), the role/lifecycle matrix, the pre-body gate (closed → 409 before
any parse), count and byte quotas under the Business lock, storage-failure
compensation, expiration boundaries, admin preview, and response hygiene
(no storage key, path, or checksum ever leaves the API).

Uploads go through the real HTTP stack (TestClient); quota-boundary and
compensation cases seed rows/objects directly for speed (docs/06:
direct policy evidence over hundreds of slow uploads).
"""

import io
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.domains.media import policies
from app.domains.media.storage import LocalFilesystemStorage, object_key
from tests.security.conftest import (
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

_SHA = "0" * 63 + "a"


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/media"


def _jpeg(width: int = 800, height: int = 600) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _upload(
    client: TestClient,
    csrf: str,
    business_id: uuid.UUID,
    content: bytes | None = None,
    *,
    filename: str = "dish.jpg",
    content_type: str = "image/jpeg",
) -> Any:
    return client.post(
        _base(business_id),
        files={"file": (filename, content if content is not None else _jpeg(), content_type)},
        headers=csrf_headers(csrf),
    )


def _seed_owner(
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
    *,
    status: str = "active",
    slug: str = "med-biz",
) -> uuid.UUID:
    business_id = create_business(slug=slug, status=status)
    owner_id = create_user(email=OWNER)
    create_membership(business_id, owner_id, role="owner")
    return business_id


def _seed_asset(
    engine: Engine,
    business_id: uuid.UUID,
    *,
    status: str = "active",
    expires: str | None = None,
    byte_size: int = 5000,
    variants: int = 2,
) -> uuid.UUID:
    asset_id = uuid.uuid4()
    expiry_sql = (
        expires
        if expires is not None
        else ("now() + interval '48 hours'" if status == "pending" else "NULL")
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                # S608: expiry_sql is one of two test-internal literals, never
                # external input.
                "INSERT INTO media_assets (id, business_id, kind, status,"  # noqa: S608
                " pending_expires_at, original_filename, declared_content_type,"
                " source_format, width, height, byte_size, checksum_sha256)"
                f" VALUES (:id, :bid, 'image', :status, {expiry_sql}, 'seed.jpg',"
                " 'image/jpeg', 'jpeg', 800, 600, :bytes, :sha)"
            ),
            {"id": asset_id, "bid": business_id, "status": status, "bytes": byte_size, "sha": _SHA},
        )
        for index in range(variants):
            connection.execute(
                text(
                    "INSERT INTO media_asset_variants (id, business_id, asset_id,"
                    " variant, width, height, byte_size, checksum_sha256) VALUES"
                    " (:id, :bid, :aid, :variant, 320, 240, :bytes, :sha)"
                ),
                {
                    "id": uuid.uuid4(),
                    "bid": business_id,
                    "aid": asset_id,
                    "variant": policies.VARIANT_NAMES[index],
                    "bytes": 1000,
                    "sha": _SHA,
                },
            )
    return asset_id


class TestUploadPipeline:
    def test_upload_creates_pending_asset_with_variants(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        response = _upload(client, csrf, business_id, _jpeg(1000, 500))
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert body["kind"] == "image"
        assert body["pending_expires_at"] is not None
        assert body["source_format"] == "jpeg"
        assert body["width"] == 1000
        # 1000px canonical -> w320 + w640 variants (w1280 skipped).
        assert {v["variant"] for v in body["variants"]} == {"w320", "w640"}
        # Response hygiene: no storage key, path, or checksum.
        assert "checksum" not in response.text.lower()
        assert "storage" not in response.text.lower()

    def test_uploaded_object_is_previewable(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        asset_id = _upload(client, csrf, business_id).json()["id"]
        preview = client.get(f"{_base(business_id)}/{asset_id}/file/canonical")
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/webp"
        assert preview.headers["x-content-type-options"] == "nosniff"
        assert preview.content[:4] == b"RIFF"  # WebP

    def test_non_image_upload_is_422(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        response = _upload(client, csrf, business_id, b"not an image at all")
        assert response.status_code == 422

    def test_animated_webp_is_422(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        frames = [Image.new("RGB", (64, 64), (i * 40, 0, 0)) for i in range(3)]
        buffer = io.BytesIO()
        frames[0].save(buffer, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
        response = _upload(
            client,
            csrf,
            business_id,
            buffer.getvalue(),
            filename="anim.webp",
            content_type="image/webp",
        )
        assert response.status_code == 422


class TestAuthorizationMatrix:
    def _business_with_roles(
        self,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> uuid.UUID:
        business_id = create_business(slug="med-authz", status="active")
        create_membership(business_id, create_user(email=OWNER), role="owner")
        create_membership(business_id, create_user(email=MANAGER), role="manager")
        create_membership(business_id, create_user(email=STAFF), role="staff")
        return business_id

    def test_manager_can_upload(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = self._business_with_roles(create_user, create_business, create_membership)
        csrf = login_as(client, MANAGER)
        assert _upload(client, csrf, business_id).status_code == 201

    def test_staff_cannot_upload_but_can_read(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = self._business_with_roles(create_user, create_business, create_membership)
        asset_id = _seed_asset(migrated_engine, business_id)
        csrf = login_as(client, STAFF)
        assert _upload(client, csrf, business_id).status_code == 403
        # Staff read/list/preview is allowed (business.view).
        assert client.get(_base(business_id)).status_code == 200
        assert client.get(f"{_base(business_id)}/{asset_id}").status_code == 200

    def test_platform_admin_without_membership_gets_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        asset_id = _seed_asset(migrated_engine, business_id)
        create_user(email=PLATFORM_ADMIN, is_platform_admin=True)
        csrf = login_as(client, PLATFORM_ADMIN)
        assert client.get(_base(business_id)).status_code == 404
        assert client.get(f"{_base(business_id)}/{asset_id}").status_code == 404
        assert _upload(client, csrf, business_id).status_code == 404

    def test_anonymous_is_401(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        assert client.get(_base(business_id)).status_code == 401

    def test_cross_tenant_asset_is_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_a = _seed_owner(create_user, create_business, create_membership, slug="med-a")
        business_b = create_business(slug="med-b", status="active")
        create_membership(business_b, create_user(email=INTRUDER), role="owner")
        asset_a = _seed_asset(migrated_engine, business_a)
        # Owner of B cannot read A's asset through B's route... nor A's route.
        csrf_b = login_as(client, INTRUDER)
        assert client.get(f"{_base(business_b)}/{asset_a}").status_code == 404
        assert client.get(f"{_base(business_a)}/{asset_a}").status_code == 404
        assert _upload(client, csrf_b, business_a).status_code == 404

    def test_upload_without_csrf_is_403(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        login_as(client, OWNER)
        response = client.post(
            _base(business_id),
            files={"file": ("x.jpg", _jpeg(), "image/jpeg")},
            headers={"Origin": "http://testserver"},  # no CSRF token
        )
        assert response.status_code == 403


class TestLifecycleGate:
    @pytest.mark.parametrize("status", ["provisioning", "active", "suspended"])
    def test_writable_lifecycle_states_allow_upload(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        status: str,
    ) -> None:
        business_id = _seed_owner(
            create_user, create_business, create_membership, status=status, slug=f"med-{status}"
        )
        csrf = login_as(client, OWNER)
        assert _upload(client, csrf, business_id).status_code == 201

    def test_closed_business_rejects_upload_before_parsing_the_body(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        # provisioning first (activation requires an owner), then close.
        business_id = _seed_owner(
            create_user, create_business, create_membership, status="suspended", slug="med-closed"
        )
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'closed' WHERE id = :id"),
                {"id": business_id},
            )
        csrf = login_as(client, OWNER)
        # A deliberately MALFORMED multipart body: receiving 409 (not 422)
        # proves the gate ran before any body parsing (final correction F).
        response = client.post(
            _base(business_id),
            content=b"garbage-not-multipart",
            headers={
                **csrf_headers(csrf),
                "Content-Type": "multipart/form-data; boundary=X",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state"
        # No asset row was created.
        with migrated_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM media_assets WHERE business_id = :id"),
                {"id": business_id},
            ).scalar_one()
        assert count == 0


class TestListGetDelete:
    def test_list_pagination_and_status_filter(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        _seed_asset(migrated_engine, business_id, status="active")
        _seed_asset(migrated_engine, business_id, status="pending")
        login_as(client, OWNER)
        page = client.get(_base(business_id), params={"limit": 10, "offset": 0}).json()
        assert page["total"] == 2
        assert len(page["items"]) == 2
        active = client.get(_base(business_id), params={"status": "active"}).json()
        assert active["total"] == 1
        assert active["items"][0]["status"] == "active"

    def test_delete_removes_row_and_objects(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        app: FastAPI,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        asset_id = _upload(client, csrf, business_id).json()["id"]
        storage: LocalFilesystemStorage = app.state.media_storage
        assert (
            storage.stat(key=object_key(business_id, uuid.UUID(asset_id), "canonical")) is not None
        )
        response = client.delete(f"{_base(business_id)}/{asset_id}", headers=csrf_headers(csrf))
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        assert client.get(f"{_base(business_id)}/{asset_id}").status_code == 404
        assert storage.stat(key=object_key(business_id, uuid.UUID(asset_id), "canonical")) is None

    def test_preview_missing_variant_is_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        # A 200x200 image gets no variants; w320 preview must 404.
        asset_id = _upload(client, csrf, business_id, _jpeg(200, 200)).json()["id"]
        assert client.get(f"{_base(business_id)}/{asset_id}/file/w320").status_code == 404
        assert client.get(f"{_base(business_id)}/{asset_id}/file/canonical").status_code == 200

    def test_preview_unknown_variant_name_is_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        asset_id = _seed_asset(migrated_engine, business_id)
        login_as(client, OWNER)
        assert client.get(f"{_base(business_id)}/{asset_id}/file/w9999").status_code == 404


class TestQuotas:
    def test_count_quota_rejects_the_501st_asset(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        # Seed exactly 500 assets with set-based SQL (fast).
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO media_assets (id, business_id, kind, status,"
                    " pending_expires_at, original_filename, declared_content_type,"
                    " source_format, width, height, byte_size, checksum_sha256)"
                    " SELECT gen_random_uuid(), :bid, 'image', 'active', NULL,"
                    " 'seed.jpg', 'image/jpeg', 'jpeg', 10, 10, 100, :sha"
                    " FROM generate_series(1, :n)"
                ),
                {"bid": business_id, "sha": _SHA, "n": policies.MAX_MEDIA_ASSETS_PER_BUSINESS},
            )
        csrf = login_as(client, OWNER)
        response = _upload(client, csrf, business_id)
        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "conflict"
        assert body["error"]["details"]["limit"] == policies.MAX_MEDIA_ASSETS_PER_BUSINESS

    def test_byte_quota_rejects_when_over_budget(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        # One asset already at (1 GiB - 1 KiB); the new upload's bytes push over.
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO media_assets (id, business_id, kind, status,"
                    " pending_expires_at, original_filename, declared_content_type,"
                    " source_format, width, height, byte_size, checksum_sha256)"
                    " VALUES (gen_random_uuid(), :bid, 'image', 'active', NULL,"
                    " 'big.jpg', 'image/jpeg', 'jpeg', 100, 100, :bytes, :sha)"
                ),
                {
                    "bid": business_id,
                    "bytes": policies.MAX_MEDIA_BYTES_PER_BUSINESS - 1024,
                    "sha": _SHA,
                },
            )
        csrf = login_as(client, OWNER)
        response = _upload(client, csrf, business_id)
        assert response.status_code == 409
        assert response.json()["error"]["details"]["limit"] == policies.MAX_MEDIA_BYTES_PER_BUSINESS

    def test_count_quota_is_race_safe_under_the_business_lock(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
        app: FastAPI,
    ) -> None:
        """Two-session boundary test (M3B pattern): at 499 assets, session A
        holds the Business lock mid-transaction while B blocks, then B is
        rejected — no over-admission (final correction E)."""
        from app.domains.businesses.queries import lock_business_status

        business_id = _seed_owner(create_user, create_business, create_membership)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO media_assets (id, business_id, kind, status,"
                    " pending_expires_at, original_filename, declared_content_type,"
                    " source_format, width, height, byte_size, checksum_sha256)"
                    " SELECT gen_random_uuid(), :bid, 'image', 'active', NULL,"
                    " 'seed.jpg', 'image/jpeg', 'jpeg', 10, 10, 100, :sha"
                    " FROM generate_series(1, :n)"
                ),
                {"bid": business_id, "sha": _SHA, "n": policies.MAX_MEDIA_ASSETS_PER_BUSINESS - 1},
            )
        # Session A holds the Business row lock (simulating an in-flight
        # upload's final transaction).
        factory = sessionmaker(bind=migrated_engine)
        session_a = factory()
        try:
            lock_business_status(session_a, business_id)  # FOR UPDATE, uncommitted

            result: dict[str, Any] = {}

            def _b_upload() -> None:
                csrf = login_as(client, OWNER)
                response = _upload(client, csrf, business_id)
                result["status"] = response.status_code

            thread = threading.Thread(target=_b_upload)
            thread.start()
            time.sleep(1.0)  # B should be blocked on the lock, not finished
            assert "status" not in result, "B must block on the Business lock"
            session_a.rollback()  # release the lock (A did not add an asset)
            thread.join(timeout=10)
        finally:
            session_a.close()
        # With A releasing without adding, B fills the 500th slot: 201.
        assert result["status"] == 201


class TestCompensation:
    def test_storage_put_failure_leaves_no_row_and_cleans_up(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        """An injected failing adapter: the DB has no asset row, and the
        temp work dir is left clean (final corrections G/N)."""
        business_id = _seed_owner(create_user, create_business, create_membership)
        real_storage: LocalFilesystemStorage = app.state.media_storage

        class FailingStorage:
            root = real_storage.root

            def put(self, **kwargs: Any) -> None:
                raise OSError("disk on fire")

            def delete(self, **kwargs: Any) -> None:
                real_storage.delete(**kwargs)

            def open(self, **kwargs: Any) -> Any:
                return real_storage.open(**kwargs)

            def stat(self, **kwargs: Any) -> Any:
                return real_storage.stat(**kwargs)

        # A non-raising client so an unhandled storage error surfaces as the
        # opaque 500 envelope (production behavior) rather than re-raising.
        client = TestClient(app, raise_server_exceptions=False)
        app.state.media_storage = FailingStorage()
        try:
            with client:
                csrf = login_as(client, OWNER)
                response = _upload(client, csrf, business_id)
        finally:
            app.state.media_storage = real_storage
        assert response.status_code == 500
        with migrated_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM media_assets WHERE business_id = :id"),
                {"id": business_id},
            ).scalar_one()
        assert count == 0
        # The encoded temp files were cleaned up (only the readiness probe
        # dir may exist, and it must be empty of leftover encode files).
        tmp = Path(real_storage.root) / ".tmp"
        leftovers = (
            [p for p in tmp.iterdir() if p.name.startswith("encode-")] if tmp.exists() else []
        )
        assert leftovers == []


class TestItemImageAttachment:
    def _seed_item(self, engine: Engine, business_id: uuid.UUID) -> uuid.UUID:
        category_id = uuid.uuid4()
        item_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (:id, :bid, 'Mains', 0, true)"
                ),
                {"id": category_id, "bid": business_id},
            )
            connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " VALUES (:id, :bid, :cid, 'Kacchi', 1500, 0, true, false, false)"
                ),
                {"id": item_id, "bid": business_id, "cid": category_id},
            )
        return item_id

    def _item_url(self, business_id: uuid.UUID, item_id: uuid.UUID) -> str:
        return f"/api/v1/businesses/{business_id}/catalog/items/{item_id}/image"

    def test_attach_promotes_pending_to_active(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        asset_id = _upload(client, csrf, business_id).json()["id"]
        item_id = self._seed_item(migrated_engine, business_id)
        response = client.post(
            self._item_url(business_id, item_id),
            json={"media_id": asset_id, "alt_text": "Chicken kacchi biryani"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["image_media_id"] == asset_id
        assert body["image_alt_text"] == "Chicken kacchi biryani"
        # The asset is now active (ever-attached).
        assert client.get(f"{_base(business_id)}/{asset_id}").json()["status"] == "active"

    def test_exact_no_op_changes_nothing(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        asset_id = _upload(client, csrf, business_id).json()["id"]
        item_id = self._seed_item(migrated_engine, business_id)
        first = client.post(
            self._item_url(business_id, item_id),
            json={"media_id": asset_id, "alt_text": "Alt"},
            headers=csrf_headers(csrf),
        ).json()
        # Re-send identical values: updated_at must not change, no new audit.
        with migrated_engine.connect() as connection:
            before = connection.execute(
                text(
                    "SELECT count(*) FROM audit_events WHERE action = 'catalog.item_image_changed'"
                )
            ).scalar_one()
        second = client.post(
            self._item_url(business_id, item_id),
            json={"media_id": asset_id, "alt_text": "Alt"},
            headers=csrf_headers(csrf),
        ).json()
        assert second["updated_at"] == first["updated_at"]
        with migrated_engine.connect() as connection:
            after = connection.execute(
                text(
                    "SELECT count(*) FROM audit_events WHERE action = 'catalog.item_image_changed'"
                )
            ).scalar_one()
        assert after == before, "an exact no-op records no audit event"

    def test_referenced_asset_cannot_be_deleted(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        asset_id = _upload(client, csrf, business_id).json()["id"]
        item_id = self._seed_item(migrated_engine, business_id)
        client.post(
            self._item_url(business_id, item_id),
            json={"media_id": asset_id},
            headers=csrf_headers(csrf),
        )
        # Referenced -> 409.
        blocked = client.delete(f"{_base(business_id)}/{asset_id}", headers=csrf_headers(csrf))
        assert blocked.status_code == 409
        # Clear the reference, then deletion succeeds.
        client.post(
            self._item_url(business_id, item_id),
            json={"media_id": None},
            headers=csrf_headers(csrf),
        )
        assert (
            client.delete(
                f"{_base(business_id)}/{asset_id}", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )

    def test_expired_pending_cannot_be_attached(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        # A pending asset already expired (past pending_expires_at).
        asset_id = _seed_asset(
            migrated_engine, business_id, status="pending", expires="now() - interval '1 minute'"
        )
        item_id = self._seed_item(migrated_engine, business_id)
        csrf = login_as(client, OWNER)
        response = client.post(
            self._item_url(business_id, item_id),
            json={"media_id": str(asset_id)},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state"

    def test_cross_tenant_media_reference_is_rejected(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_a = _seed_owner(create_user, create_business, create_membership, slug="att-a")
        business_b = create_business(slug="att-b", status="active")
        asset_b = _seed_asset(migrated_engine, business_b)
        item_a = self._seed_item(migrated_engine, business_a)
        csrf = login_as(client, OWNER)
        response = client.post(
            self._item_url(business_a, item_a),
            json={"media_id": str(asset_b)},
            headers=csrf_headers(csrf),
        )
        # B's asset is invisible in A's tenant -> 404 (non-disclosure).
        assert response.status_code == 404

    def test_alt_updated_records_equal_media_id_pair(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        asset_id = _upload(client, csrf, business_id).json()["id"]
        item_id = self._seed_item(migrated_engine, business_id)
        client.post(
            self._item_url(business_id, item_id),
            json={"media_id": asset_id, "alt_text": "First"},
            headers=csrf_headers(csrf),
        )
        client.post(
            self._item_url(business_id, item_id),
            json={"media_id": asset_id, "alt_text": "Second"},
            headers=csrf_headers(csrf),
        )
        with migrated_engine.connect() as connection:
            stored = connection.execute(
                text(
                    "SELECT details FROM audit_events"
                    " WHERE action = 'catalog.item_image_changed'"
                    " ORDER BY id DESC LIMIT 1"
                )
            ).scalar_one()
        assert stored["change"] == "alt_updated"
        assert stored["media_id_old"] == asset_id
        assert stored["media_id_new"] == asset_id
        assert stored["alt_text_changed"] == "changed"
        # Alt text itself is never stored.
        assert "First" not in str(stored)
        assert "Second" not in str(stored)


class TestResponseHygiene:
    def test_no_storage_key_path_or_checksum_in_any_response(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        app: FastAPI,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        csrf = login_as(client, OWNER)
        created = _upload(client, csrf, business_id)
        asset_id = created.json()["id"]
        storage: LocalFilesystemStorage = app.state.media_storage
        root_fragment = str(storage.root)
        for response in (
            created,
            client.get(_base(business_id)),
            client.get(f"{_base(business_id)}/{asset_id}"),
        ):
            text_body = response.text
            assert root_fragment not in text_body
            assert ".webp" not in text_body  # keys/paths never surface
            assert "checksum" not in text_body.lower()
