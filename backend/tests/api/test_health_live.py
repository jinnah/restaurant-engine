"""Liveness probe contract."""

from fastapi.testclient import TestClient


def test_health_live_returns_200_alive(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_live_is_not_under_api_v1(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").status_code == 404
