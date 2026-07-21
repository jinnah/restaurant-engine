"""Pre-body upload-gate rejection matrix (M3C, ADR-017, correction 6/F).

For every non-authorized actor class, a deliberately MALFORMED multipart
upload is rejected with the gate-specific status (never the multipart
422), proving the auth / CSRF / capability / lifecycle gate ran before any
body was parsed. Each case also proves zero side effects: no storage call,
no media row, no media audit event, and no leaked scratch file.
"""

import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

OWNER = "owner@example.com"
STAFF = "staff@example.com"
PLATFORM_ADMIN = "admin@example.com"
OTHER_OWNER = "other-owner@example.com"

# A body that is NOT valid multipart: if the gate let it reach parsing, the
# result would be a 422, so any gate status here proves pre-parse rejection.
_MALFORMED_BODY = b"garbage-not-a-real-multipart-body"
_MALFORMED_CT = {"Content-Type": "multipart/form-data; boundary=XYZ"}


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/media"


class _RecordingStorage:
    """Wraps the real adapter and counts every storage operation."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls = 0
        self.root = inner.root

    def put(self, **kwargs: Any) -> None:
        self.calls += 1
        self._inner.put(**kwargs)

    def open(self, **kwargs: Any) -> Any:
        self.calls += 1
        return self._inner.open(**kwargs)

    def delete(self, **kwargs: Any) -> None:
        self.calls += 1
        self._inner.delete(**kwargs)

    def stat(self, **kwargs: Any) -> Any:
        self.calls += 1
        return self._inner.stat(**kwargs)


def _assert_no_side_effects(
    engine: Engine,
    business_id: uuid.UUID,
    storage: _RecordingStorage,
    scratch_dir: Path,
) -> None:
    assert storage.calls == 0, "the gate must reject before any storage call"
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT count(*) FROM media_assets WHERE business_id = :bid"),
            {"bid": business_id},
        ).scalar_one()
        events = connection.execute(
            text(
                "SELECT count(*) FROM audit_events"
                " WHERE action = 'media.asset_uploaded' AND business_id = :bid"
            ),
            {"bid": business_id},
        ).scalar_one()
    assert rows == 0
    assert events == 0
    if scratch_dir.exists():
        leaked = [
            path.name
            for path in scratch_dir.iterdir()
            if path.name.startswith(("upload-", "encode-"))
        ]
        assert leaked == [], f"no scratch file must leak: {leaked}"


class TestPreBodyGateMatrix:
    @staticmethod
    def _post(client: TestClient, business_id: uuid.UUID, headers: dict[str, str]) -> Any:
        return client.post(
            _base(business_id), content=_MALFORMED_BODY, headers={**headers, **_MALFORMED_CT}
        )

    def test_anonymous_is_401_before_parsing(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="pb-anon", status="active")
        create_membership(business_id, create_user(email=OWNER), role="owner")
        spy = _RecordingStorage(app.state.media_storage)
        app.state.media_storage = spy
        scratch_dir: Path = app.state.media_scratch_dir
        with TestClient(app) as client:
            response = self._post(client, business_id, {"Origin": "http://testserver"})
        assert response.status_code == 401
        _assert_no_side_effects(migrated_engine, business_id, spy, scratch_dir)

    def test_missing_csrf_is_403_before_parsing(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="pb-csrf0", status="active")
        create_membership(business_id, create_user(email=OWNER), role="owner")
        spy = _RecordingStorage(app.state.media_storage)
        app.state.media_storage = spy
        scratch_dir: Path = app.state.media_scratch_dir
        with TestClient(app) as client:
            login_as(client, OWNER)  # authenticated, but no CSRF token sent
            response = self._post(client, business_id, {"Origin": "http://testserver"})
        assert response.status_code == 403
        _assert_no_side_effects(migrated_engine, business_id, spy, scratch_dir)

    def test_invalid_csrf_is_403_before_parsing(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="pb-csrf1", status="active")
        create_membership(business_id, create_user(email=OWNER), role="owner")
        spy = _RecordingStorage(app.state.media_storage)
        app.state.media_storage = spy
        scratch_dir: Path = app.state.media_scratch_dir
        with TestClient(app) as client:
            login_as(client, OWNER)
            response = self._post(
                client,
                business_id,
                {"Origin": "http://testserver", "X-CSRF-Token": "wrong-token"},
            )
        assert response.status_code == 403
        _assert_no_side_effects(migrated_engine, business_id, spy, scratch_dir)

    def test_staff_is_403_before_parsing(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="pb-staff", status="active")
        create_membership(business_id, create_user(email=STAFF), role="staff")
        spy = _RecordingStorage(app.state.media_storage)
        app.state.media_storage = spy
        scratch_dir: Path = app.state.media_scratch_dir
        with TestClient(app) as client:
            csrf = login_as(client, STAFF)
            response = self._post(client, business_id, csrf_headers(csrf))
        assert response.status_code == 403
        _assert_no_side_effects(migrated_engine, business_id, spy, scratch_dir)

    def test_platform_admin_without_membership_is_404_before_parsing(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="pb-plat", status="active")
        create_membership(business_id, create_user(email=OWNER), role="owner")
        create_user(email=PLATFORM_ADMIN, is_platform_admin=True)
        spy = _RecordingStorage(app.state.media_storage)
        app.state.media_storage = spy
        scratch_dir: Path = app.state.media_scratch_dir
        with TestClient(app) as client:
            csrf = login_as(client, PLATFORM_ADMIN)
            response = self._post(client, business_id, csrf_headers(csrf))
        assert response.status_code == 404
        _assert_no_side_effects(migrated_engine, business_id, spy, scratch_dir)

    def test_nonmember_owner_is_404_before_parsing(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_a = create_business(slug="pb-a", status="active")
        create_membership(business_a, create_user(email=OWNER), role="owner")
        business_b = create_business(slug="pb-b", status="active")
        create_membership(business_b, create_user(email=OTHER_OWNER), role="owner")
        spy = _RecordingStorage(app.state.media_storage)
        app.state.media_storage = spy
        scratch_dir: Path = app.state.media_scratch_dir
        with TestClient(app) as client:
            csrf = login_as(client, OTHER_OWNER)  # owner of B, not of A
            response = self._post(client, business_a, csrf_headers(csrf))
        assert response.status_code == 404
        _assert_no_side_effects(migrated_engine, business_a, spy, scratch_dir)

    def test_closed_business_is_409_before_parsing(
        self,
        app: FastAPI,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business(slug="pb-closed", status="suspended")
        create_membership(business_id, create_user(email=OWNER), role="owner")
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'closed' WHERE id = :id"),
                {"id": business_id},
            )
        spy = _RecordingStorage(app.state.media_storage)
        app.state.media_storage = spy
        scratch_dir: Path = app.state.media_scratch_dir
        with TestClient(app) as client:
            csrf = login_as(client, OWNER)
            response = self._post(client, business_id, csrf_headers(csrf))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state"
        _assert_no_side_effects(migrated_engine, business_id, spy, scratch_dir)
