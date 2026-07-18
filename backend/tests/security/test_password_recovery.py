"""Password recovery (M2D, ADR-014): issuance authority, two-phase
redemption, session revocation, and uniform non-disclosure.

Runs against real PostgreSQL (locks, partial uniques, and SQL-clock expiry
are the subject under test).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core import security
from tests.security.conftest import (
    BROWSER_HEADERS,
    STANDARD_PASSWORD,
    CreateUser,
    csrf_headers,
    login,
    login_as,
)

_ISSUE = "/api/v1/platform/password-resets"
_REDEEM = "/api/v1/password-resets/redeem"
_NEW_PASSWORD = "an entirely new pw 42!"

ADMIN = "admin@example.com"
TARGET = "owner@example.com"


def _admin_csrf(client: TestClient, create_user: CreateUser) -> str:
    create_user(ADMIN, is_platform_admin=True)
    return login_as(client, ADMIN)


def _issue(client: TestClient, csrf: str, email: str = TARGET) -> Any:
    return client.post(_ISSUE, json={"email": email}, headers=csrf_headers(csrf))


def _redeem(client: TestClient, token: str, password: str = _NEW_PASSWORD) -> Any:
    return client.post(
        _REDEEM, json={"token": token, "new_password": password}, headers=BROWSER_HEADERS
    )


class TestIssuance:
    def test_issue_returns_raw_token_once_with_expiry(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        response = _issue(client, csrf)
        assert response.status_code == 201, response.text
        body = response.json()
        assert set(body) == {"token", "expires_at", "email"}
        assert body["email"] == TARGET
        # Stored form is the SHA-256 digest, never the raw token.
        with migrated_engine.connect() as connection:
            stored = connection.execute(
                text("SELECT token_hash FROM password_reset_tokens")
            ).scalar_one()
        assert stored == security.hash_opaque_token(body["token"])
        assert stored != body["token"]

    def test_issuance_is_audited_without_the_token(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        token = _issue(client, csrf).json()["token"]
        with migrated_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT details::text AS details FROM audit_events"
                    " WHERE action = 'auth.password_reset_issued'"
                )
            ).one()
        assert TARGET in row.details
        assert token not in row.details
        assert security.hash_opaque_token(token) not in row.details

    def test_non_admin_cannot_issue(self, client: TestClient, create_user: CreateUser) -> None:
        create_user(TARGET)
        csrf = login_as(client, TARGET)
        assert _issue(client, csrf).status_code == 403

    def test_unknown_email_is_404(self, client: TestClient, create_user: CreateUser) -> None:
        csrf = _admin_csrf(client, create_user)
        assert _issue(client, csrf, email="nobody@example.com").status_code == 404

    def test_inactive_account_is_409(self, client: TestClient, create_user: CreateUser) -> None:
        create_user(TARGET, is_active=False)
        csrf = _admin_csrf(client, create_user)
        response = _issue(client, csrf)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state"

    def test_reissue_revokes_the_predecessor(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        first = _issue(client, csrf).json()["token"]
        second = _issue(client, csrf).json()["token"]
        # The superseded token is dead; the new one works.
        assert _redeem(client, first).status_code == 404
        assert _redeem(client, second).status_code == 200


class TestRedemption:
    def test_happy_path_sets_password_and_revokes_sessions(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user(TARGET, failed_login_count=3, last_failed_seconds_ago=10.0)
        csrf = _admin_csrf(client, create_user)
        token = _issue(client, csrf).json()["token"]

        # The target logs in on another client; that session must die.
        with TestClient(client.app) as victim:
            assert login(victim, email=TARGET).status_code == 200
            assert victim.get("/api/v1/auth/session").status_code == 200

            assert _redeem(client, token).status_code == 200

            # Old session revoked; old password dead; new password works;
            # backoff pair cleared.
            assert victim.get("/api/v1/auth/session").status_code == 401
        with TestClient(client.app) as fresh:
            assert login(fresh, email=TARGET, password=STANDARD_PASSWORD).status_code == 401
            assert login(fresh, email=TARGET, password=_NEW_PASSWORD).status_code == 200
        with migrated_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT failed_login_count, last_failed_login_at, used_at"
                    " FROM users JOIN password_reset_tokens"
                    " ON users.id = password_reset_tokens.user_id"
                )
            ).one()
        assert row.failed_login_count == 0
        assert row.last_failed_login_at is None
        assert row.used_at is not None

    def test_single_use(self, client: TestClient, create_user: CreateUser) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        token = _issue(client, csrf).json()["token"]
        assert _redeem(client, token).status_code == 200
        second = _redeem(client, token, password="another fine password 7!")
        assert second.status_code == 404
        assert second.json()["error"]["code"] == "not_found"

    def test_invalid_and_expired_tokens_are_uniform_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        migrated_engine: Engine,
    ) -> None:
        user_id = create_user(TARGET)
        admin_id = create_user(ADMIN, is_platform_admin=True)
        # Insert an already-expired token directly (created in the past so
        # the expires-after-creation CHECK holds).
        expired_raw = security.generate_opaque_token()
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO password_reset_tokens (id, user_id, token_hash,"
                    " issued_by_user_id, created_at, expires_at) VALUES"
                    " (gen_random_uuid(), :uid, :th, :aid,"
                    " now() - interval '2 hours', now() - interval '1 hour')"
                ),
                {"uid": user_id, "th": security.hash_opaque_token(expired_raw), "aid": admin_id},
            )
        garbage = security.generate_opaque_token()
        for raw in (expired_raw, garbage):
            response = _redeem(client, raw)
            assert response.status_code == 404
            body = response.json()["error"]
            assert body["code"] == "not_found"
            assert body["message"] == "Reset token is not valid or has expired."

    def test_inactive_user_cannot_redeem(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user_id = create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        token = _issue(client, csrf).json()["token"]
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE users SET is_active = false WHERE id = :uid"), {"uid": user_id}
            )
        assert _redeem(client, token).status_code == 404

    def test_password_policy_applies_at_redemption(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        token = _issue(client, csrf).json()["token"]
        assert _redeem(client, token, password="short").status_code == 422
        # The failed attempt consumed nothing.
        assert _redeem(client, token).status_code == 200


class TestArgonPrevalidation:
    """Correction A: invalid tokens must never reach the KDF."""

    @pytest.fixture
    def hash_counter(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        calls: list[str] = []
        original = security.hash_password

        def counting(password: str) -> str:
            calls.append("hash")
            return original(password)

        # The recovery module resolves security.hash_password at call time,
        # so patching the source module intercepts exactly its KDF calls
        # (login uses verify_password, which is untouched).
        monkeypatch.setattr("app.core.security.hash_password", counting)
        return calls

    def test_invalid_expired_revoked_used_tokens_skip_argon2(
        self,
        client: TestClient,
        create_user: CreateUser,
        migrated_engine: Engine,
        hash_counter: list[str],
    ) -> None:
        user_id = create_user(TARGET)
        admin_id = create_user(ADMIN, is_platform_admin=True)
        expired_raw = security.generate_opaque_token()
        revoked_raw = security.generate_opaque_token()
        used_raw = security.generate_opaque_token()
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO password_reset_tokens (id, user_id, token_hash,"
                    " issued_by_user_id, created_at, expires_at, used_at, revoked_at) VALUES"
                    " (gen_random_uuid(), :uid, :expired, :aid, now() - interval '2 hours',"
                    "  now() - interval '1 hour', NULL, NULL),"
                    " (gen_random_uuid(), :uid2, :revoked, :aid, now(),"
                    "  now() + interval '1 hour', NULL, now()),"
                    " (gen_random_uuid(), :uid3, :used, :aid, now(),"
                    "  now() + interval '1 hour', now(), NULL)"
                ),
                {
                    "uid": user_id,
                    "uid2": create_user("second@example.com"),
                    "uid3": create_user("third@example.com"),
                    "expired": security.hash_opaque_token(expired_raw),
                    "revoked": security.hash_opaque_token(revoked_raw),
                    "used": security.hash_opaque_token(used_raw),
                    "aid": admin_id,
                },
            )
        for raw in (expired_raw, revoked_raw, used_raw, security.generate_opaque_token()):
            assert _redeem(client, raw).status_code == 404
        assert hash_counter == [], "invalid tokens must never invoke Argon2"

    def test_valid_token_does_invoke_argon2_once(
        self, client: TestClient, create_user: CreateUser, hash_counter: list[str]
    ) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        token = _issue(client, csrf).json()["token"]
        assert _redeem(client, token).status_code == 200
        assert hash_counter == ["hash"], "positive control: the happy path hashes exactly once"


class TestTokenHygiene:
    def test_raw_token_never_appears_in_logs(
        self,
        client: TestClient,
        create_user: CreateUser,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        token = _issue(client, csrf).json()["token"]
        assert _redeem(client, token).status_code == 200
        captured = capsys.readouterr()
        assert token not in captured.out
        assert token not in captured.err

    def test_issue_response_is_no_store(self, client: TestClient, create_user: CreateUser) -> None:
        create_user(TARGET)
        csrf = _admin_csrf(client, create_user)
        response = _issue(client, csrf)
        assert response.headers["cache-control"] == "no-store"


def test_break_glass_cli_still_exists() -> None:
    """The bootstrap CLI remains the documented break-glass for a locked-out
    sole platform administrator (ADR-014)."""
    from app.domains.identity.service import create_platform_admin

    assert callable(create_platform_admin)


def test_admin_on_admin_reset_is_allowed(client: TestClient, create_user: CreateUser) -> None:
    """Ruling K: resets may target another platform administrator, with the
    same audit trail — no special-casing that could strand a sole admin."""
    create_user("other-admin@example.com", is_platform_admin=True)
    csrf = _admin_csrf(client, create_user)
    response = _issue(client, csrf, email="other-admin@example.com")
    assert response.status_code == 201
