"""Preview stream closure through the real HTTP/route path (round-2 finding 1).

Complements the ASGI-lifecycle unit tests: this drives the actual
``media_asset_file_get`` endpoint via the TestClient and proves the
route's own wiring (the ``_stream_and_close`` generator plus the
response-level ``BackgroundTask``) closes the underlying object stream.
"""

import io
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

OWNER = "owner@example.com"


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/media"


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), (200, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


class _CountingStream:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)
        self.close_count = 0

    def read(self, size: int) -> bytes:
        return self._buf.read(size)

    def close(self) -> None:
        self.close_count += 1


def test_preview_endpoint_closes_the_object_stream(
    app: FastAPI,
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
) -> None:
    business_id = create_business(slug="prev-close", status="active")
    create_membership(business_id, create_user(email=OWNER), role="owner")
    real_storage = app.state.media_storage

    with TestClient(app) as client:
        csrf = login_as(client, OWNER)
        asset_id = client.post(
            _base(business_id),
            files={"file": ("dish.jpg", _jpeg(), "image/jpeg")},
            headers=csrf_headers(csrf),
        ).json()["id"]

        # Read the real canonical bytes, then inject a counting stream so the
        # response streams valid WebP while we observe closure.
        from app.domains.media.storage import object_key

        key = object_key(business_id, uuid.UUID(asset_id), "canonical")
        with real_storage.open(key=key) as handle:
            data = handle.read()
        counting = _CountingStream(data)

        class _StreamSpyStorage:
            root = real_storage.root

            def open(self, **_kwargs: Any) -> Any:
                return counting

            def put(self, **kwargs: Any) -> None:  # pragma: no cover
                real_storage.put(**kwargs)

            def delete(self, **kwargs: Any) -> None:  # pragma: no cover
                real_storage.delete(**kwargs)

            def stat(self, **kwargs: Any) -> Any:
                return real_storage.stat(**kwargs)

        app.state.media_storage = _StreamSpyStorage()
        try:
            response = client.get(f"{_base(business_id)}/{asset_id}/file/canonical")
        finally:
            app.state.media_storage = real_storage

    assert response.status_code == 200
    assert response.content == data
    assert counting.close_count >= 1
