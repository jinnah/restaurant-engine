"""Upload commit/compensation boundary and worker-thread isolation.

Final correction 1 (the row-to-object invariant): a failure that
definitely precedes commit compensates every written object; a commit
that succeeds and then raises keeps the committed row and its objects; an
ambiguous commit outcome that cannot be reconciled never deletes
potentially-referenced objects.

Final correction 2 (worker isolation): multipart extraction and Pillow
processing run off the event-loop thread.
"""

import asyncio
import io
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, text

from app.domains.media import policies, service
from app.domains.media.processing import process_image as real_process_image
from app.domains.media.service_support import safe_commit as real_safe_commit
from app.domains.media.storage import LocalFilesystemStorage, object_key
from app.domains.media.upload import extract_single_file as real_extract_single_file
from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

OWNER = "owner@example.com"
_SHA = "0" * 63 + "a"


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/media"


def _jpeg(width: int = 800, height: int = 600) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _seed_owner(
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
    *,
    slug: str = "comp-biz",
) -> uuid.UUID:
    business_id = create_business(slug=slug, status="active")
    create_membership(business_id, create_user(email=OWNER), role="owner")
    return business_id


def _upload(client: TestClient, csrf: str, business_id: uuid.UUID) -> Any:
    return client.post(
        _base(business_id),
        files={"file": ("dish.jpg", _jpeg(1000, 500), "image/jpeg")},
        headers=csrf_headers(csrf),
    )


def _stored_objects(storage: LocalFilesystemStorage) -> list[str]:
    return [stat.key for stat in storage.iter_objects()]


def _uploaded_events(engine: Engine, business_id: uuid.UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    "SELECT count(*) FROM audit_events WHERE action = 'media.asset_uploaded'"
                    " AND business_id = :bid"
                ),
                {"bid": business_id},
            ).scalar_one()
        )


class TestCompensationBoundary:
    def test_precommit_quota_rejection_removes_objects_and_leaves_no_row(
        self,
        app: FastAPI,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        # Seed exactly the cap of assets (no objects on disk).
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
        storage: LocalFilesystemStorage = app.state.media_storage
        assert _stored_objects(storage) == []  # precondition
        csrf = login_as(client, OWNER)

        response = _upload(client, csrf, business_id)
        assert response.status_code == 409

        # The quota check precedes commit → the written objects are removed,
        # no row was added, and no upload audit event was recorded.
        assert _stored_objects(storage) == []
        with migrated_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM media_assets WHERE business_id = :bid"),
                {"bid": business_id},
            ).scalar_one()
        assert count == policies.MAX_MEDIA_ASSETS_PER_BUSINESS
        assert _uploaded_events(migrated_engine, business_id) == 0

    def test_commit_succeeds_then_raises_keeps_row_audit_and_objects(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
        monkeypatch: Any,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        storage: LocalFilesystemStorage = app.state.media_storage

        def commit_then_raise(db: Any) -> None:
            real_safe_commit(db)  # the row + audit are durably persisted...
            raise RuntimeError("post-commit boom")  # ...then a later step fails

        monkeypatch.setattr(service, "safe_commit", commit_then_raise)

        client = TestClient(app, raise_server_exceptions=False)
        with client:
            csrf = login_as(client, OWNER)
            response = _upload(client, csrf, business_id)
        assert response.status_code == 500

        # The committed row, its audit event, and every object survive: an
        # ambiguous post-commit failure must never delete referenced objects.
        with migrated_engine.connect() as connection:
            row = connection.execute(
                text("SELECT id, status FROM media_assets WHERE business_id = :bid"),
                {"bid": business_id},
            ).one()
        assert row.status == "pending"
        assert _uploaded_events(migrated_engine, business_id) == 1
        assert storage.stat(key=object_key(business_id, row.id, "canonical")) is not None

    def test_ambiguous_commit_that_cannot_be_reconciled_retains_objects(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
        monkeypatch: Any,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        storage: LocalFilesystemStorage = app.state.media_storage

        def commit_raises(db: Any) -> None:
            db.rollback()  # nothing persists in this simulation
            raise RuntimeError("ambiguous commit outcome")

        # Absence cannot be proved → objects must be retained, never deleted.
        monkeypatch.setattr(service, "safe_commit", commit_raises)
        monkeypatch.setattr(service, "_asset_row_absent", lambda *a, **k: False)

        client = TestClient(app, raise_server_exceptions=False)
        with client:
            csrf = login_as(client, OWNER)
            response = _upload(client, csrf, business_id)
        assert response.status_code == 500

        # No row (the simulation rolled back), but the objects are RETAINED
        # because absence could not be positively proved (correction 1).
        with migrated_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM media_assets WHERE business_id = :bid"),
                {"bid": business_id},
            ).scalar_one()
        assert count == 0
        assert len(_stored_objects(storage)) >= 1


class TestWorkerThreadIsolation:
    def test_extraction_and_processing_run_off_the_event_loop(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        monkeypatch: Any,
    ) -> None:
        business_id = _seed_owner(create_user, create_business, create_membership)
        observed: dict[str, bool] = {}

        def _loop_running() -> bool:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return False
            return True

        def spy_extract(*args: Any, **kwargs: Any) -> Any:
            observed["extract_on_loop"] = _loop_running()
            return real_extract_single_file(*args, **kwargs)

        def spy_process(*args: Any, **kwargs: Any) -> Any:
            observed["process_on_loop"] = _loop_running()
            return real_process_image(*args, **kwargs)

        monkeypatch.setattr(service, "extract_single_file", spy_extract)
        monkeypatch.setattr(service, "process_image", spy_process)

        client = TestClient(app)
        with client:
            csrf = login_as(client, OWNER)
            assert _upload(client, csrf, business_id).status_code == 201

        # A running asyncio loop exists only on the event-loop thread; its
        # absence proves both ran in the AnyIO worker thread (correction 2).
        assert observed["extract_on_loop"] is False
        assert observed["process_on_loop"] is False
