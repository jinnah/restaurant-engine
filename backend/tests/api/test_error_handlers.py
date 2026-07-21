"""Every error response uses the ADR-008 envelope."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.correlation import REQUEST_ID_HEADER
from app.main import create_app
from tests.conftest import make_settings


@pytest.fixture
def app_with_probes() -> FastAPI:
    """App plus test-only routes that trigger validation and server errors."""
    app = create_app(make_settings())

    @app.get("/__probe__/items/{item_id}")
    def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/__probe__/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest.fixture
def client(app_with_probes: FastAPI) -> TestClient:
    return TestClient(app_with_probes, raise_server_exceptions=False)


def test_unknown_route_returns_not_found_envelope(client: TestClient) -> None:
    response = client.get("/no-such-route", headers={REQUEST_ID_HEADER: "corr-404"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "field_errors": [],
            "correlation_id": "corr-404",
            "details": None,
        }
    }


def test_wrong_method_returns_method_not_allowed_envelope(client: TestClient) -> None:
    response = client.post("/health/live")
    assert response.status_code == 405
    body = response.json()
    assert body["error"]["code"] == "method_not_allowed"
    assert body["error"]["correlation_id"] == response.headers[REQUEST_ID_HEADER]


def test_validation_failure_returns_field_errors(client: TestClient) -> None:
    response = client.get("/__probe__/items/not-a-number")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed."
    (field_error,) = body["error"]["field_errors"]
    assert field_error["field"] == "path.item_id"
    assert field_error["code"] == "int_parsing"
    assert field_error["message"]


def test_unhandled_exception_returns_opaque_internal_error(client: TestClient) -> None:
    response = client.get("/__probe__/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "An internal error occurred."
    # Internals must never leak into the response.
    assert "secret internal detail" not in response.text
    assert "RuntimeError" not in response.text
    assert body["error"]["correlation_id"] == response.headers[REQUEST_ID_HEADER]


def test_unhandled_exception_is_never_cacheable(client: TestClient) -> None:
    """The 500 handler renders outside the middleware stack (M3D).

    Starlette runs the ``Exception`` handler in its outermost
    ServerErrorMiddleware, so ``NoStoreApiMiddleware`` — which stamps the
    cache policy while wrapping ``send`` — never sees this response. The
    handler sets the header itself; without that, an unhandled failure
    would be the one response on the whole API carrying no cache policy.
    """
    assert client.get("/__probe__/boom").headers["cache-control"] == "no-store"
