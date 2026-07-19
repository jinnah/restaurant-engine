"""The E2E database reset script touches only its allowlisted database.

Safety first: the script must refuse — before opening any connection —
every target except the exact literal ``restaurant_engine_e2e``. The
functional half proves ``--recreate`` produces a head-migrated database
and ``--drop`` removes it. Subprocess isolation mirrors the bootstrap
regression: the script is exercised exactly as its caller (the E2E
orchestrator) runs it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.conftest import TEST_DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parents[2]
E2E_DB = "restaurant_engine_e2e"
E2E_URL = make_url(TEST_DATABASE_URL).set(database=E2E_DB)


def _run(mode: str, database_url: str | None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    env.pop("DATABASE_URL", None)
    if database_url is not None:
        env["DATABASE_URL"] = database_url
    return subprocess.run(  # noqa: S603 - argv is sys.executable plus literals
        [sys.executable, "-m", "scripts.reset_e2e_database", mode],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        env=env,
        timeout=180,
    )


@pytest.mark.parametrize(
    "target",
    [
        "restaurant_engine",  # the development database
        "restaurant_engine_test",  # the standing test database
        "restaurant_engine_e2e_2",  # near-miss name
        "postgres",
    ],
)
def test_refuses_every_non_allowlisted_database(target: str) -> None:
    url = make_url(TEST_DATABASE_URL).set(database=target)
    for mode in ("--recreate", "--drop"):
        result = _run(mode, url.render_as_string(hide_password=False))
        assert result.returncode == 2, result.stderr
        assert "refusing to touch database" in result.stderr
        assert target in result.stderr


def test_refuses_missing_and_malformed_database_url() -> None:
    missing = _run("--recreate", None)
    assert missing.returncode == 2
    assert "must be set explicitly" in missing.stderr

    malformed = _run("--drop", "not a database url ::")
    assert malformed.returncode == 2
    assert "not a valid database url" in malformed.stderr.lower()


def test_recreate_then_drop_lifecycle(test_database_url: str) -> None:
    url_str = E2E_URL.render_as_string(hide_password=False)

    result = _run("--recreate", url_str)
    assert result.returncode == 0, result.stderr
    assert "recreated" in result.stdout

    engine = create_engine(url_str, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            versions = connection.execute(text("SELECT version_num FROM alembic_version")).all()
            assert len(versions) == 1
            tables = connection.execute(
                text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
            ).scalar()
            assert tables == 9
    finally:
        engine.dispose()

    # Recreate is idempotent from a dirty starting state.
    again = _run("--recreate", url_str)
    assert again.returncode == 0, again.stderr

    dropped = _run("--drop", url_str)
    assert dropped.returncode == 0, dropped.stderr
    assert "dropped" in dropped.stdout

    admin = create_engine(
        E2E_URL.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": E2E_DB},
            ).scalar()
            assert exists is None
    finally:
        admin.dispose()
