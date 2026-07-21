"""Readiness against the real PostgreSQL database."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_ready_returns_200_with_database_up(test_database_url: str) -> None:
    client = TestClient(create_app(make_settings(database_url=test_database_url)))
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": {"status": "up"},
            "media_storage": {"status": "up"},
        },
    }
