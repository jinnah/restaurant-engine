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
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
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
        # M2B schema: identity/audit (M2A) + tenancy (businesses, memberships).
        assert tables == {
            "alembic_version",
            "users",
            "sessions",
            "audit_events",
            "businesses",
            "memberships",
        }
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
    """Pre-production policy: every M2 migration ships a working downgrade.

    Runs only against the throwaway scratch database from ``empty_database_url``
    — never the preserved development database (approved amendment 10).
    """
    config = _config(empty_database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()

    command.upgrade(config, "head")  # and the chain still applies afterwards


# The M2A revision (down_revision of the M2B tenancy migration); downgrading
# the M2B migration lands here.
_M2A_REVISION = "91774776ff27"


def test_tenancy_downgrade_preserves_audit_rows(empty_database_url: str) -> None:
    """Audit-preserving downgrade (approved amendment 1), scratch DB only.

    Create a real tenant-scoped audit event, downgrade to M2A, and prove the
    audit row survives — nulled and restored to the M2A ``restaurant_id``
    column name (never deleted, never dangling); then re-upgrade to M2B
    successfully.
    """
    config = _config(empty_database_url)
    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        # A business and a tenant-scoped audit event referencing it.
        with engine.begin() as connection:
            business_id = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'Audit Fixture', 'audit-fixture', 'provisioning')"
                    " RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO audit_events (occurred_at, action, business_id,"
                    " target_type, target_id) VALUES (now(), 'business.created', :bid,"
                    " 'business', :tid)"
                ),
                {"bid": business_id, "tid": str(business_id)},
            )
            audit_id = connection.execute(
                text("SELECT id FROM audit_events WHERE action = 'business.created'")
            ).scalar_one()

        # Downgrade to M2A: the audit row must remain; the tenant column is
        # nulled and restored to its M2A restaurant_id name.
        command.downgrade(config, _M2A_REVISION)
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT action, restaurant_id FROM audit_events WHERE id = :id"),
                {"id": audit_id},
            ).one()
        assert row.action == "business.created"
        assert row.restaurant_id is None
        assert "businesses" not in set(inspect(engine).get_table_names())

        # Re-upgrade to M2B succeeds (the FK re-applies over the nulled rows).
        command.upgrade(config, "head")
        assert "businesses" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_model_metadata_matches_migrated_schema(empty_database_url: str) -> None:
    """ORM metadata and the migrated schema are identical (review M-1 guard).

    Migrate a scratch database to head and diff it against the complete
    declarative metadata with Alembic's autogenerate comparison. Any
    difference — a constraint or FK present in only one of the two, a type
    or server-default mismatch — fails here, so model/migration drift can
    never ship silently again.
    """
    # Import every model module so Base.metadata is complete (mirrors
    # migrations/env.py; a missing import would hide tables from the diff).
    from app.core.database import Base
    from app.domains.audit import models as _audit_models  # noqa: F401
    from app.domains.businesses import models as _businesses_models  # noqa: F401
    from app.domains.identity import models as _identity_models  # noqa: F401

    config = _config(empty_database_url)
    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "compare_server_default": True},
            )
            diffs = compare_metadata(context, Base.metadata)
        assert diffs == [], f"ORM metadata and migrated schema differ: {diffs}"
    finally:
        engine.dispose()
