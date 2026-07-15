"""Migration behavior against a real, empty PostgreSQL database.

Proves the Milestone 1 exit criterion: `alembic upgrade head` runs from an
empty database. A dedicated scratch database is created fresh for each run
so the test is deterministic and never touches development or test data.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import TEST_DATABASE_URL

SCRATCH_DB = "restaurant_engine_migration_scratch"


@pytest.fixture
def empty_database_url(test_database_url: str) -> Iterator[str]:
    """A freshly created, empty scratch database, dropped afterwards."""
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
        connection.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    try:
        # str(URL) obfuscates the password; render it fully for real use.
        yield url.set(database=SCRATCH_DB).render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin_engine.dispose()


def test_upgrade_head_runs_on_empty_database(empty_database_url: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", empty_database_url)

    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        tables = inspect(engine).get_table_names()
        # The baseline is empty: bookkeeping table only, no product schema.
        assert tables == ["alembic_version"]
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "96b88c334395"
    finally:
        engine.dispose()


def test_upgrade_head_is_idempotent_at_head(empty_database_url: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", empty_database_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # a second run is a no-op, not an error
