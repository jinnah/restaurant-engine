"""Session lifecycle security (M2A, ADR-010).

Rotation, revocation, idle and absolute expiry, inactive-user rejection,
cookie mechanics (flags, clearing on invalid presentation), storage
hygiene (hash only), and the opportunistic dead-session cleanup.
"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core import security
from tests.security.conftest import BROWSER_HEADERS, CreateUser, login


def _sessions(engine: Engine) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT * FROM sessions ORDER BY created_at")).all())


def _age_session(engine: Engine, *, created_days: float, last_used_hours: float) -> None:
    """Rewrite the (single) session row's clock so expiries can be tested."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE sessions SET"
                " created_at = now() - (:created_days * interval '1 day'),"
                " last_used_at = now() - (:last_used_hours * interval '1 hour'),"
                " absolute_expires_at ="
                "   now() - (:created_days * interval '1 day') + interval '30 days'"
            ),
            {"created_days": created_days, "last_used_hours": last_used_hours},
        )


def _insert_session(
    engine: Engine,
    user_id: uuid.UUID,
    *,
    revoked: bool = False,
    expired: bool = False,
) -> str:
    token = security.generate_opaque_token()
    with engine.begin() as connection:
        connection.execute(
            # S608: fixture-internal SQL; interpolated fragments are fixed
            # literals selected by the two booleans, never external input.
            text(
                "INSERT INTO sessions (id, user_id, token_hash, csrf_token, created_at,"  # noqa: S608
                " last_used_at, absolute_expires_at, revoked_at) VALUES"
                " (:id, :user_id, :token_hash, :csrf_token,"
                "  now() - interval '10 days', now() - interval '1 minute',"
                f"  now() {'- ' if expired else '+ '}interval '1 hour',"
                f"  {'now()' if revoked else 'NULL'})"
            ),
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "token_hash": security.hash_opaque_token(token),
                "csrf_token": security.generate_opaque_token(),
            },
        )
    return token


class TestCookieContract:
    def test_development_cookie_flags(self, client: TestClient, create_user: CreateUser) -> None:
        create_user()
        set_cookie = login(client).headers["set-cookie"]
        assert set_cookie.startswith("session=")
        lowered = set_cookie.lower()
        assert "httponly" in lowered
        assert "samesite=lax" in lowered
        assert "path=/" in lowered
        assert "max-age=2592000" in lowered  # 30 days
        assert "secure" not in lowered  # development runs over plain HTTP
        assert "domain=" not in lowered

    def test_production_cookie_name_and_secure_flag(self) -> None:
        # Settings-level proof (the full app needs no production boot here).
        from tests.conftest import make_settings

        settings = make_settings(
            app_env="production",
            database_url="postgresql+psycopg://app:distinct-real-secret@db:5432/app",
            trusted_origins="https://admin.example.com",
        )
        assert settings.session_cookie_name == "__Host-session"
        assert settings.session_cookie_secure is True

    def test_invalid_presented_cookie_is_cleared_on_401(self, client: TestClient) -> None:
        client.cookies.set("session", "forged-or-stale-token")
        response = client.get("/api/v1/auth/session")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"
        set_cookie = response.headers["set-cookie"].lower()
        assert set_cookie.startswith("session=")
        assert "max-age=0" in set_cookie or "expires" in set_cookie

    def test_missing_cookie_is_401_without_deletion(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/session")
        assert response.status_code == 401
        assert "set-cookie" not in response.headers


class TestSessionResolution:
    def test_login_then_session_roundtrip(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        user_id = create_user()
        csrf_from_login = login(client).json()["csrf_token"]
        response = client.get("/api/v1/auth/session")
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["id"] == str(user_id)
        assert body["csrf_token"] == csrf_from_login

    def test_each_login_issues_a_fresh_token(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        first_cookie = login(client).cookies["session"]
        second_cookie = login(client).cookies["session"]
        assert first_cookie != second_cookie
        assert len(_sessions(migrated_engine)) == 2  # concurrent devices allowed

    def test_only_the_token_hash_is_stored(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        raw_token = login(client).cookies["session"]
        rows = _sessions(migrated_engine)
        assert len(rows) == 1
        assert rows[0].token_hash == security.hash_opaque_token(raw_token)
        assert raw_token not in str(rows[0])

    def test_inactive_user_sessions_stop_working(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user_id = create_user()
        login(client)
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE users SET is_active = false WHERE id = :id"), {"id": user_id}
            )
        assert client.get("/api/v1/auth/session").status_code == 401


class TestExpiry:
    def test_idle_expiry(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        login(client)
        _age_session(migrated_engine, created_days=2, last_used_hours=25)  # idle 24h exceeded
        assert client.get("/api/v1/auth/session").status_code == 401

    def test_absolute_expiry_despite_recent_activity(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        login(client)
        _age_session(migrated_engine, created_days=31, last_used_hours=1)  # 30d absolute exceeded
        assert client.get("/api/v1/auth/session").status_code == 401

    def test_last_used_is_refreshed_beyond_the_write_threshold(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        login(client)
        _age_session(migrated_engine, created_days=0.5, last_used_hours=2)
        assert client.get("/api/v1/auth/session").status_code == 200
        with migrated_engine.connect() as connection:
            seconds_since_use = connection.execute(
                text("SELECT extract(epoch FROM now() - last_used_at) FROM sessions")
            ).scalar()
        assert seconds_since_use is not None and float(seconds_since_use) < 60


class TestLogout:
    def _login_and_logout(self, client: TestClient) -> Any:
        csrf_token = login(client).json()["csrf_token"]
        return client.post(
            "/api/v1/auth/logout",
            headers={**BROWSER_HEADERS, "X-CSRF-Token": csrf_token},
        )

    def test_logout_revokes_and_clears(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        response = self._login_and_logout(client)
        assert response.status_code == 200
        assert response.json() == {"status": "logged_out"}
        assert "max-age=0" in response.headers["set-cookie"].lower()
        assert _sessions(migrated_engine)[0].revoked_at is not None
        # The revoked session no longer authenticates even if replayed.
        assert client.get("/api/v1/auth/session").status_code == 401

    def test_logout_is_audited(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user()
        self._login_and_logout(client)
        with migrated_engine.connect() as connection:
            actions = list(
                connection.execute(text("SELECT action FROM audit_events ORDER BY id")).scalars()
            )
        assert actions == ["auth.login_succeeded", "auth.logout"]


class TestSessionHygiene:
    def test_login_sweeps_that_users_dead_sessions(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user_id = create_user()
        other_user = create_user("other@example.com")
        _insert_session(migrated_engine, user_id, revoked=True)
        _insert_session(migrated_engine, user_id, expired=True)
        keep_other = _insert_session(migrated_engine, other_user)  # not ours: untouched

        login(client)

        rows = _sessions(migrated_engine)
        token_hashes = {row.token_hash for row in rows}
        assert len(rows) == 2  # the fresh session + the other user's
        assert security.hash_opaque_token(keep_other) in token_hashes

    def test_revoke_all_sessions_service_mechanism(
        self, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        # Wired to password reset / deactivation in M2D; mechanism proven now.
        from sqlalchemy.orm import Session as OrmSession

        from app.domains.identity.service import revoke_all_sessions

        user_id = create_user()
        _insert_session(migrated_engine, user_id)
        _insert_session(migrated_engine, user_id)
        with OrmSession(migrated_engine) as db:
            revoked = revoke_all_sessions(db, user_id=user_id)
            db.commit()
        assert revoked == 2
        assert all(row.revoked_at is not None for row in _sessions(migrated_engine))
