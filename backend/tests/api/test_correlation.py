"""Correlation-ID contract."""

import uuid

from fastapi.testclient import TestClient

from app.core.correlation import REQUEST_ID_HEADER, get_request_id


def test_generated_id_when_header_absent(client: TestClient) -> None:
    response = client.get("/health/live")
    request_id = response.headers[REQUEST_ID_HEADER]
    assert uuid.UUID(request_id)  # generated IDs are UUIDs


def test_valid_inbound_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health/live", headers={REQUEST_ID_HEADER: "edge-proxy_1.42"})
    assert response.headers[REQUEST_ID_HEADER] == "edge-proxy_1.42"


def test_unsafe_inbound_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={REQUEST_ID_HEADER: "bad id\twith spaces"})
    replaced = response.headers[REQUEST_ID_HEADER]
    assert replaced != "bad id\twith spaces"
    assert uuid.UUID(replaced)


def test_oversized_inbound_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={REQUEST_ID_HEADER: "a" * 65})
    assert uuid.UUID(response.headers[REQUEST_ID_HEADER])


def test_contextvar_is_clear_outside_requests() -> None:
    assert get_request_id() is None
