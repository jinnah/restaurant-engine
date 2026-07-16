"""Login security behavior (M2A, ADR-010).

Covers the approved contract: uniform failure responses (no account
existence or throttle-state disclosure), backoff instead of lockout,
counter semantics (attempts inside the window neither count nor extend),
and audit side effects committed on rejected attempts.
"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.security.conftest import BROWSER_HEADERS, STANDARD_PASSWORD, CreateUser, login


def _user_row(engine: Engine, user_id: uuid.UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT failed_login_count, last_failed_login_at, password_hash"
                " FROM users WHERE id = :id"
            ),
            {"id": user_id},
        ).one()


def _audit_actions(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(text("SELECT action FROM audit_events ORDER BY id")).scalars()
        )


def _session_count(engine: Engine) -> int:
    with engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM sessions")).scalar()
        assert count is not None
        return int(count)


class TestSuccessfulLogin:
    def test_returns_identity_csrf_and_session_cookie(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user_id = create_user("owner@example.com", is_platform_admin=True)
        response = login(client)
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["id"] == str(user_id)
        assert body["user"]["email"] == "owner@example.com"
        assert body["user"]["is_platform_admin"] is True
        assert len(body["csrf_token"]) >= 43
        assert "session=" in response.headers["set-cookie"]
        assert _audit_actions(migrated_engine) == ["auth.login_succeeded"]

    def test_email_is_normalized_for_lookup(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user("owner@example.com")
        assert login(client, email="  OWNER@Example.COM ").status_code == 200

    def test_success_resets_backoff_state(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user_id = create_user(failed_login_count=4, last_failed_seconds_ago=3600)
        assert login(client).status_code == 200
        row = _user_row(migrated_engine, user_id)
        assert row.failed_login_count == 0
        assert row.last_failed_login_at is None


class TestUniformFailure:
    """Every failure path is externally identical (addendum item 4 method)."""

    REQUEST_ID = "uniform-failure-comparison"

    def _login_body(self, client: TestClient, email: str, password: str) -> tuple[int, Any, str]:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={**BROWSER_HEADERS, "X-Request-ID": self.REQUEST_ID},
        )
        return response.status_code, response.json(), response.headers.get("set-cookie", "")

    def test_all_failure_modes_are_indistinguishable(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user("real@example.com")
        create_user("inactive@example.com", is_active=False)
        create_user("throttled@example.com", failed_login_count=8, last_failed_seconds_ago=0.0)

        outcomes = [
            self._login_body(client, "ghost@example.com", "irrelevant-password"),
            self._login_body(client, "real@example.com", "wrong-password-here"),
            self._login_body(client, "inactive@example.com", STANDARD_PASSWORD),
            self._login_body(client, "throttled@example.com", STANDARD_PASSWORD),
        ]

        statuses = {status for status, _, _ in outcomes}
        assert statuses == {401}
        bodies = [body for _, body, _ in outcomes]
        assert all(body == bodies[0] for body in bodies[1:]), (
            "login failure bodies differ between failure modes"
        )
        assert bodies[0]["error"]["code"] == "invalid_credentials"
        assert bodies[0]["error"]["correlation_id"] == self.REQUEST_ID
        # No failure path may ever set a cookie.
        assert {cookie for _, _, cookie in outcomes} == {""}

    def test_no_session_row_is_created_on_failure(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        login(client, password="wrong-password-here")
        login(client, email="ghost@example.com")
        assert _session_count(migrated_engine) == 0


class TestBackoffCounter:
    def test_wrong_password_increments_atomically(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user_id = create_user()
        login(client, password="wrong-password-here")
        login(client, password="wrong-password-here")
        row = _user_row(migrated_engine, user_id)
        assert row.failed_login_count == 2
        assert row.last_failed_login_at is not None

    def test_attempts_inside_the_window_do_not_count_or_extend(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user_id = create_user(failed_login_count=6, last_failed_seconds_ago=0.0)
        before = _user_row(migrated_engine, user_id)
        login(client, password="wrong-password-here")
        login(client, password=STANDARD_PASSWORD)
        after = _user_row(migrated_engine, user_id)
        assert after.failed_login_count == before.failed_login_count == 6
        assert after.last_failed_login_at == before.last_failed_login_at

    def test_correct_password_inside_the_window_is_still_rejected(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        # The real hash is never consulted inside the window — otherwise
        # backoff would not slow guessing (addendum item 1).
        create_user(failed_login_count=8, last_failed_seconds_ago=0.0)
        assert login(client).status_code == 401

    def test_window_elapses_and_correct_login_succeeds(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        # 5 failures -> 1s window; a failure 30s ago is well outside it.
        create_user(failed_login_count=5, last_failed_seconds_ago=30.0)
        assert login(client).status_code == 200

    def test_under_threshold_never_throttles(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user(failed_login_count=4, last_failed_seconds_ago=0.0)
        assert login(client).status_code == 200


class TestFailureAudit:
    def test_each_failure_mode_writes_its_audit_event(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user("real@example.com")
        create_user("throttled@example.com", failed_login_count=8, last_failed_seconds_ago=0.0)

        login(client, email="ghost@example.com")  # unknown -> login_failed
        login(client, email="real@example.com", password="wrong-password-here")
        login(client, email="throttled@example.com")  # inside window

        assert _audit_actions(migrated_engine) == [
            "auth.login_failed",
            "auth.login_failed",
            "auth.login_throttled",
        ]

    def test_audit_details_never_contain_password_material(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        secret = "wrong-but-still-secret-password"
        login(client, password=secret)
        with migrated_engine.connect() as connection:
            payloads = connection.execute(
                text("SELECT coalesce(details::text, '') FROM audit_events")
            ).scalars()
            joined = " ".join(payloads)
        assert secret not in joined
        assert STANDARD_PASSWORD not in joined


class TestLoginInputValidation:
    def test_malformed_email_is_a_validation_error(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "whatever-here"},
            headers=BROWSER_HEADERS,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_unknown_fields_are_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@b.co", "password": "whatever-here", "admin": True},
            headers=BROWSER_HEADERS,
        )
        assert response.status_code == 422
