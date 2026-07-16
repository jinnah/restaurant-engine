"""Response and logging hygiene (M2A, ADR-010, review item R13).

no-store on the versioned API, secrets absent from bodies and logs, and
correlation-ID behavior on auth errors.
"""

import contextlib
import io

from fastapi.testclient import TestClient

from tests.security.conftest import CreateUser, login


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

    def test_login_flow_never_logs_password_or_token(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        # structlog's PrintLoggerFactory writes to stdout; capture the whole
        # flow (success + failure) and assert no secret material leaks.
        create_user()
        secret_password = "super-secret-wrong-pass"
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            success = login(client)
            login(client, password=secret_password)
            client.get("/api/v1/auth/session")
        output = captured.getvalue()
        assert secret_password not in output
        assert success.cookies["session"] not in output
        assert success.json()["csrf_token"] not in output


class TestAuthErrorEnvelope:
    def test_auth_errors_carry_the_injected_correlation_id(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/session", headers={"X-Request-ID": "auth-corr-check"})
        assert response.status_code == 401
        assert response.json()["error"]["correlation_id"] == "auth-corr-check"
        assert response.headers["x-request-id"] == "auth-corr-check"
