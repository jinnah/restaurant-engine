"""The documented platform-admin bootstrap command works standalone.

The defect this guards against: the script's own import graph must load
the COMPLETE model registry. ``audit_events.business_id`` references
``businesses.id``, so a script that imports only the identity-side
models cannot flush — SQLAlchemy raises ``NoReferencedTableError``. The
full application (and any test that imports it) masks the gap, which is
exactly why this test invokes the script in a fresh subprocess: nothing
the test process imported can leak into the script's registry.

Runs against a dedicated scratch database at the current Alembic head —
never the development or standing test database.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.conftest import TEST_DATABASE_URL

SCRATCH_DB = "restaurant_engine_bootstrap_scratch"
BACKEND_DIR = Path(__file__).resolve().parents[2]

EMAIL = "bootstrap.smoke@smoke.example"
DISPLAY_NAME = "Bootstrap Smoke Admin"
PASSWORD = "a bootstrap-only pw 7731!"


@pytest.fixture
def bootstrap_database_url() -> Iterator[str]:
    """A scratch database migrated to head, dropped afterwards."""
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
        connection.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    scratch_url = url.set(database=SCRATCH_DB).render_as_string(hide_password=False)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", scratch_url)
    command.upgrade(config, "head")
    try:
        yield scratch_url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin_engine.dispose()


def _run_script(database_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke the documented CLI exactly as an operator would.

    A fresh interpreter with only the script's own imports: the strongest
    proof that the script resolves the complete model registry itself.
    The password travels via the documented stdin mechanism, never argv.
    """
    argv = [
        sys.executable,
        "-m",
        "scripts.create_platform_admin",
        "--email",
        EMAIL,
        "--display-name",
        DISPLAY_NAME,
        "--password-stdin",
    ]
    assert PASSWORD not in " ".join(argv)
    return subprocess.run(  # noqa: S603 - argv is sys.executable plus literals
        argv,
        input=PASSWORD + "\n",
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        timeout=180,
    )


def test_bootstrap_script_works_in_isolation(bootstrap_database_url: str) -> None:
    result = _run_script(bootstrap_database_url)

    assert result.returncode == 0, result.stderr
    assert f"created platform admin {EMAIL}" in result.stdout
    # The password never appears in any captured output stream.
    assert PASSWORD not in result.stdout
    assert PASSWORD not in result.stderr

    engine = create_engine(bootstrap_database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            users = connection.execute(
                text("SELECT email, display_name, is_platform_admin, password_hash FROM users")
            ).all()
            assert len(users) == 1
            email, display_name, is_admin, password_hash = users[0]
            assert email == EMAIL
            assert display_name == DISPLAY_NAME
            assert is_admin is True
            # Stored as an Argon2 hash, never plaintext.
            assert password_hash.startswith("$argon2")
            assert PASSWORD not in password_hash

            events = connection.execute(
                text("SELECT action, actor_user_id, business_id FROM audit_events")
            ).all()
            assert len(events) == 1
            action, actor_user_id, business_id = events[0]
            assert action == "user.platform_admin_created"
            # Platform-scope bootstrap: no actor session, no tenant.
            assert actor_user_id is None
            assert business_id is None
    finally:
        engine.dispose()

    # The duplicate contract stays safe standalone too: clean failure,
    # no traceback, and still no password in any stream.
    duplicate = _run_script(bootstrap_database_url)
    assert duplicate.returncode == 1
    assert "already exists" in duplicate.stderr
    assert "Traceback" not in duplicate.stderr
    assert PASSWORD not in duplicate.stdout
    assert PASSWORD not in duplicate.stderr
