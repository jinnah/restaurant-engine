"""Readiness with an unreachable database (no infrastructure needed:
connection to a closed local port fails immediately)."""

import concurrent.futures

from fastapi.testclient import TestClient

from app.core.correlation import REQUEST_ID_HEADER
from app.domains.media.storage import LocalFilesystemStorage
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
            # The database is down; the (temp) media root is writable and up.
            "details": {"checks": {"database": "down", "media_storage": "up"}},
        }
    }
    assert response.headers[REQUEST_ID_HEADER] == "ready-drill-1"


def test_liveness_is_unaffected_by_database_outage() -> None:
    client = TestClient(create_app(make_settings(database_url=UNREACHABLE_URL)))
    assert client.get("/health/live").status_code == 200


def test_ready_reports_media_storage_down_without_exposing_the_path(tmp_path) -> None:
    """A read-only/unwritable media root fails the check with no path leak."""
    app = create_app(make_settings(media_storage_root=str(tmp_path / "media")))
    # Replace the storage with one whose probe always fails.
    app.state.media_storage = LocalFilesystemStorage(tmp_path / "media")
    original_probe = app.state.media_storage.probe

    def _boom() -> None:
        raise OSError("disk full")

    app.state.media_storage.probe = _boom  # type: ignore[method-assign]
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["details"]["checks"]["media_storage"] == "down"
    # The media root path never appears anywhere in the response.
    assert str(tmp_path) not in response.text
    app.state.media_storage.probe = original_probe  # type: ignore[method-assign]


def test_concurrent_readiness_probes_do_not_collide(tmp_path) -> None:
    """Collision-safe probe: many parallel readiness checks all pass and
    leave no marker behind (unique probe names, finally cleanup)."""
    storage = LocalFilesystemStorage(tmp_path / "media")
    storage.root.mkdir(parents=True)

    def _probe() -> None:
        for _ in range(20):
            storage.probe()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_probe) for _ in range(8)]
        for future in futures:
            future.result()  # no exception

    tmp_dir = storage.root / ".tmp"
    assert not any(tmp_dir.iterdir()) if tmp_dir.exists() else True
