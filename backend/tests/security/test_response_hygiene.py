"""Response and logging hygiene (M2A, ADR-010, review item R13).

no-store on the versioned API, secrets absent from bodies and logs, and
correlation-ID behavior on auth errors.
"""

import structlog
from fastapi.testclient import TestClient

from app.core.logging import configure_logging
from app.main import create_app
from tests.conftest import make_settings
from tests.security.conftest import (
    STANDARD_PASSWORD,
    TRUSTED_ORIGIN,
    CreateUser,
    login,
)


class TestNoStore:
    def test_api_responses_are_never_cacheable(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user()
        success = login(client)
        assert success.headers["cache-control"] == "no-store"
        error = client.get("/api/v1/auth/session")  # 401 path included
        assert error.headers["cache-control"] == "no-store"

    def test_health_probes_are_not_covered(self, client: TestClient) -> None:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert "cache-control" not in response.headers


class TestSecretHygiene:
    def test_login_body_never_contains_the_session_token(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        # The opaque token travels in the cookie only; the JSON body carries
        # the CSRF token (readable by design) and identity, nothing else.
        create_user()
        response = login(client)
        session_token = response.cookies["session"]
        assert session_token not in response.text

    def test_login_flow_logs_are_captured_and_secret_free(
        self, create_user: CreateUser, standard_password_hash: str
    ) -> None:
        """Repaired per security review M2A, MEDIUM-2.

        The app under test logs at INFO (the request events exist), the
        capture is structlog-native (``capture_logs`` swaps the processor
        chain for the duration and restores the previous configuration on
        exit), and a positive control proves the capture actually saw the
        request events before any absence assertion is trusted.
        """
        create_user()
        secret_password = "super-secret-wrong-pass"
        settings = make_settings(
            log_level="INFO",
            trusted_origins=f"{TRUSTED_ORIGIN},http://localhost:5173",
        )
        try:
            app = create_app(settings)  # configures structlog at INFO
            with (
                TestClient(app) as client,
                structlog.testing.capture_logs() as logs,
            ):
                success = login(client)
                login(client, password=secret_password)
                client.get("/api/v1/auth/session")
        finally:
            # Never leak the INFO configuration into other tests.
            configure_logging(make_settings())

        # Positive control: the capture must have seen one request event
        # per call above — otherwise the absence assertions are vacuous.
        # Note: the logged route template omits the /api/v1 prefix for
        # nested routers — pre-existing M1 logging behavior, observed here,
        # deliberately not changed in this correction.
        request_events = [entry for entry in logs if entry.get("event") == "request"]
        assert len(request_events) == 3
        assert {entry.get("route") for entry in request_events} == {
            "/auth/login",
            "/auth/session",
        }
        assert {entry.get("status") for entry in request_events} == {200, 401}

        # With capture proven live, absence is meaningful: no passwords,
        # raw session tokens (== cookie values), CSRF tokens, or password
        # hashes in any captured event.
        dump = repr(logs)
        assert secret_password not in dump
        assert STANDARD_PASSWORD not in dump
        assert success.cookies["session"] not in dump
        assert success.json()["csrf_token"] not in dump
        assert standard_password_hash not in dump


class TestAuthErrorEnvelope:
    def test_auth_errors_carry_the_injected_correlation_id(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/session", headers={"X-Request-ID": "auth-corr-check"})
        assert response.status_code == 401
        assert response.json()["error"]["correlation_id"] == "auth-corr-check"
        assert response.headers["x-request-id"] == "auth-corr-check"
