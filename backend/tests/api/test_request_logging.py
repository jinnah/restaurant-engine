"""Structured request logging behavior.

Request events are emitted at INFO, so these tests build an app whose
log level is INFO (the shared test settings use WARNING to keep other
tests quiet).
"""

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.main import create_app
from tests.conftest import make_settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(make_settings(log_level="INFO")))


def test_completed_request_emits_one_structured_event(client: TestClient) -> None:
    with capture_logs() as events:
        client.get("/health/live", headers={"X-Request-ID": "test-log-correlation"})

    requests = [e for e in events if e["event"] == "request"]
    assert len(requests) == 1
    event = requests[0]
    assert event["method"] == "GET"
    assert event["route"] == "/health/live"
    assert event["status"] == 200
    assert event["duration_ms"] >= 0
    assert event["request_id"] == "test-log-correlation"


def test_unmatched_path_logs_raw_path_with_404(client: TestClient) -> None:
    with capture_logs() as events:
        client.get("/no-such-route")

    event = next(e for e in events if e["event"] == "request")
    assert event["status"] == 404
    assert event["route"] == "/no-such-route"
