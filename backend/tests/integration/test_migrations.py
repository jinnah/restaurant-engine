"""Migration behavior against a real, empty PostgreSQL database.

Proves two permanent quality gates: `alembic upgrade head` runs from an
empty database, and every individual migration applies against the
previous head (stepwise walk, approved M2 addendum item on migration
sequencing) — not merely the whole chain against empty. A dedicated
scratch database is created fresh for each run so the test is
deterministic and never touches development or test data.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
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


def _config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _ordered_revisions(config: Config) -> list[str]:
    """All revision ids from oldest (baseline) to newest (head)."""
    script = ScriptDirectory.from_config(config)
    return [rev.revision for rev in reversed(list(script.walk_revisions("base", "heads")))]


def test_upgrade_head_runs_on_empty_database(empty_database_url: str) -> None:
    config = _config(empty_database_url)

    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        tables = set(inspect(engine).get_table_names())
        # M2A schema: the three identity/audit tables plus bookkeeping.
        assert tables == {"alembic_version", "users", "sessions", "audit_events"}
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == _ordered_revisions(config)[-1]
    finally:
        engine.dispose()


def test_upgrade_head_is_idempotent_at_head(empty_database_url: str) -> None:
    config = _config(empty_database_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # a second run is a no-op, not an error


def test_each_migration_applies_against_the_previous_head(empty_database_url: str) -> None:
    """Stepwise walk: every revision upgrades from its own down_revision.

    This is the mechanical form of the 'migration upgrade from previous
    schema succeeds' quality gate: a migration that only works on an empty
    database (or that depends on a later revision's schema) fails here.
    """
    config = _config(empty_database_url)
    for revision in _ordered_revisions(config):
        command.upgrade(config, revision)

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == _ordered_revisions(config)[-1]
    finally:
        engine.dispose()


def test_downgrades_are_real_and_reversible(empty_database_url: str) -> None:
    """Pre-production policy: every M2 migration ships a working downgrade."""
    config = _config(empty_database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()

    command.upgrade(config, "head")  # and the chain still applies afterwards
