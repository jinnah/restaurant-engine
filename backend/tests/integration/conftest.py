"""Integration fixtures: real PostgreSQL required (ADR-005).

All tests under tests/integration/ carry the ``integration`` marker and run
against the Docker Compose development server. A missing database is a hard,
explained failure — never a silent skip — so the suite cannot go green while
silently not testing the database.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from tests.conftest import TEST_DATABASE_URL


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in str(item.path).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Ensure the isolated test database exists; fail clearly when down."""
    url = make_url(TEST_DATABASE_URL)
    admin_url = url.set(database="postgres")
    admin_engine = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
    )
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        pytest.fail(
            "PostgreSQL is not reachable on 127.0.0.1:5433. "
            "Start it with `docker compose up -d db` from the repository root. "
            f"Underlying error: {type(exc).__name__}",
            pytrace=False,
        )
    finally:
        admin_engine.dispose()
    return TEST_DATABASE_URL
