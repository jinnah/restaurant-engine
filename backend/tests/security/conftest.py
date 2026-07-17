"""Security-suite fixtures (M2A): the permanent session/CSRF test bed.

Everything here runs against real PostgreSQL (docs/06: session semantics
depend on constraints and transactions), so the whole directory carries the
``integration`` marker via the collection hook. Tables are truncated before
each test; the schema comes from the real migration chain, never from
ORM ``create_all``.

Argon2 hashing is deliberately expensive, so user factories share one
precomputed hash for the standard password instead of hashing per user.
"""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from app.core import security
from app.main import create_app
from tests.conftest import make_settings

# The TestClient's own origin: requests that should *pass* the fail-closed
# browser-context check send these headers explicitly (docs/05: non-browser
# clients must present a trusted Origin).
TRUSTED_ORIGIN = "http://testserver"
BROWSER_HEADERS = {"Origin": TRUSTED_ORIGIN}

STANDARD_PASSWORD = "correct horse battery st!"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/security" in str(item.path).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def standard_password_hash() -> str:
    """One real Argon2 hash shared by every factory-created user."""
    return security.hash_password(STANDARD_PASSWORD)


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str) -> Iterator[Engine]:
    """The test database at migration head, with a session-long engine."""
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_database_url)
    command.upgrade(config, "head")
    engine = create_engine(test_database_url, connect_args={"connect_timeout": 3})
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(migrated_engine: Engine) -> None:
    """Start every test from empty identity/audit tables."""
    with migrated_engine.begin() as connection:
        connection.execute(text("TRUNCATE users, sessions, audit_events RESTART IDENTITY CASCADE"))


@pytest.fixture
def app(migrated_engine: Engine) -> FastAPI:
    """App under test: real settings, the TestClient origin trusted."""
    settings = make_settings(trusted_origins=f"{TRUSTED_ORIGIN},http://localhost:5173")
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


CreateUser = Callable[..., uuid.UUID]


@pytest.fixture
def create_user(migrated_engine: Engine, standard_password_hash: str) -> CreateUser:
    """Insert a user directly (fixture setup, not the flow under test)."""

    def _create(
        email: str = "owner@example.com",
        *,
        password_hash: str | None = None,
        is_platform_admin: bool = False,
        is_active: bool = True,
        failed_login_count: int = 0,
        last_failed_seconds_ago: float | None = None,
    ) -> uuid.UUID:
        user_id = uuid.uuid4()
        last_failed_sql = (
            "now() - make_interval(secs => :last_failed_seconds_ago)"
            if last_failed_seconds_ago is not None
            else "NULL"
        )
        params: dict[str, Any] = {
            "id": user_id,
            "email": email,
            "email_normalized": email.strip().lower(),
            "display_name": "Test User",
            "password_hash": password_hash or standard_password_hash,
            "is_platform_admin": is_platform_admin,
            "is_active": is_active,
            "failed_login_count": failed_login_count,
        }
        if last_failed_seconds_ago is not None:
            params["last_failed_seconds_ago"] = last_failed_seconds_ago
        with migrated_engine.begin() as connection:
            connection.execute(
                # S608: fixture-internal SQL; the only interpolated fragment
                # is one of two literals above, never external input.
                text(
                    "INSERT INTO users (id, email, email_normalized, display_name,"  # noqa: S608
                    " password_hash, is_platform_admin, is_active, failed_login_count,"
                    f" last_failed_login_at, created_at) VALUES (:id, :email,"
                    f" :email_normalized, :display_name, :password_hash,"
                    f" :is_platform_admin, :is_active, :failed_login_count,"
                    # created_at is backdated so any last_failed_login_at the
                    # tests choose satisfies ck_users_last_failed_login_after_creation.
                    f" {last_failed_sql}, now() - interval '30 days')"
                ),
                params,
            )
        return user_id

    return _create


def login(
    client: TestClient,
    email: str = "owner@example.com",
    password: str = STANDARD_PASSWORD,
    **kwargs: Any,
) -> Any:
    """POST /api/v1/auth/login with trusted browser-context headers."""
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=BROWSER_HEADERS,
        **kwargs,
    )
