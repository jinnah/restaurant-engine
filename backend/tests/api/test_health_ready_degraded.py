"""Readiness with an unreachable database (no infrastructure needed:
connection to a closed local port fails immediately)."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

UNREACHABLE_URL = "postgresql+psycopg://nobody:nothing@localhost:59999/absent"


def test_ready_returns_503_when_database_is_unreachable() -> None:
    client = TestClient(create_app(make_settings(database_url=UNREACHABLE_URL)))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": {"status": "down"}},
    }


def test_liveness_is_unaffected_by_database_outage() -> None:
    client = TestClient(create_app(make_settings(database_url=UNREACHABLE_URL)))
    assert client.get("/health/live").status_code == 200
