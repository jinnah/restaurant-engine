"""Readiness with an unreachable database (no infrastructure needed:
connection to a closed local port fails immediately)."""

from fastapi.testclient import TestClient

from app.core.correlation import REQUEST_ID_HEADER
from app.main import create_app
from tests.conftest import make_settings

UNREACHABLE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:59999/absent"


def test_ready_returns_503_envelope_when_database_is_unreachable() -> None:
    """Not-ready uses the ADR-008 envelope with checks preserved in details."""
    client = TestClient(create_app(make_settings(database_url=UNREACHABLE_URL)))
    response = client.get("/health/ready", headers={REQUEST_ID_HEADER: "ready-drill-1"})
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "dependency_unavailable",
            "message": "Service dependencies are unavailable.",
            "field_errors": [],
            "correlation_id": "ready-drill-1",
            "details": {"checks": {"database": "down"}},
        }
    }
    assert response.headers[REQUEST_ID_HEADER] == "ready-drill-1"


def test_liveness_is_unaffected_by_database_outage() -> None:
    client = TestClient(create_app(make_settings(database_url=UNREACHABLE_URL)))
    assert client.get("/health/live").status_code == 200
