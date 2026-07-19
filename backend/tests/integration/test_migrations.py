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
        # M2A identity/audit + M2B tenancy + M2D onboarding/recovery/
        # entitlements + M3A catalog core.
        assert tables == {
            "alembic_version",
            "users",
            "sessions",
            "audit_events",
            "businesses",
            "memberships",
            "business_invitations",
            "password_reset_tokens",
            "feature_entitlements",
            "menu_categories",
            "menu_items",
            "menu_item_dietary_tags",
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
    from app.domains.catalog import models as _catalog_models  # noqa: F401
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


# The M2C-era revision (down_revision of the M2D migration).
_M2C_ERA_REVISION = "116b4abf9a40"

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64


def test_m2d_constraints_and_round_trip_with_real_rows(empty_database_url: str) -> None:
    """M2D tables behave with real data, not only empty walks (ADR-014).

    Exercises the partial uniques, foreign-key behavior (RESTRICT and
    CASCADE), and the token-shape CHECK against seeded rows; then proves
    the downgrade drops the three tables and the chain re-applies.
    Scratch database only.
    """
    config = _config(empty_database_url)
    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, email_normalized, display_name,"
                    " password_hash, is_platform_admin, is_active, failed_login_count)"
                    " VALUES (gen_random_uuid(), 'a@x.com', 'a@x.com', 'A', 'h', true,"
                    " true, 0) RETURNING id"
                )
            )
            user_id = connection.execute(text("SELECT id FROM users LIMIT 1")).scalar_one()
            business_id = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'Fixture', 'fixture', 'active') RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO business_invitations (id, business_id, email,"
                    " email_normalized, role, token_hash, invited_by_user_id, expires_at)"
                    " VALUES (gen_random_uuid(), :bid, 'b@x.com', 'b@x.com', 'staff',"
                    " :th, :uid, now() + interval '7 days')"
                ),
                {"bid": business_id, "uid": user_id, "th": _SHA_A},
            )
            connection.execute(
                text(
                    "INSERT INTO password_reset_tokens (id, user_id, token_hash,"
                    " issued_by_user_id, expires_at) VALUES (gen_random_uuid(), :uid,"
                    " :th, :uid, now() + interval '60 minutes')"
                ),
                {"uid": user_id, "th": _SHA_B},
            )
            connection.execute(
                text(
                    "INSERT INTO feature_entitlements (id, business_id, feature_key)"
                    " VALUES (gen_random_uuid(), :bid, 'online_ordering')"
                ),
                {"bid": business_id},
            )

        def _rejected(statement: str, params: dict[str, object]) -> bool:
            with engine.begin() as connection:
                try:
                    connection.execute(text(statement), params)
                except Exception:
                    return True
            return False

        # Partial unique: a second live invitation for the same business+email.
        assert _rejected(
            "INSERT INTO business_invitations (id, business_id, email,"
            " email_normalized, role, token_hash, invited_by_user_id, expires_at)"
            " VALUES (gen_random_uuid(), :bid, 'b@x.com', 'b@x.com', 'staff',"
            " :th, :uid, now() + interval '7 days')",
            {"bid": business_id, "uid": user_id, "th": _SHA_C},
        ), "second live invitation for the same business+email must violate"
        # Partial unique: a second live reset token for the same user.
        assert _rejected(
            "INSERT INTO password_reset_tokens (id, user_id, token_hash,"
            " issued_by_user_id, expires_at) VALUES (gen_random_uuid(), :uid,"
            " :th, :uid, now() + interval '60 minutes')",
            {"uid": user_id, "th": _SHA_C},
        ), "second live reset token for the same user must violate"
        # Token-shape CHECK: a raw (non-hex) token must never be storable.
        assert _rejected(
            "INSERT INTO password_reset_tokens (id, user_id, token_hash,"
            " issued_by_user_id, expires_at) VALUES (gen_random_uuid(), :uid,"
            " 'raw-token-value', :uid, now() + interval '60 minutes')",
            {"uid": user_id},
        ), "non-SHA-256 token_hash must violate the shape CHECK"
        # Entitlement tenant-leading unique.
        assert _rejected(
            "INSERT INTO feature_entitlements (id, business_id, feature_key)"
            " VALUES (gen_random_uuid(), :bid, 'online_ordering')",
            {"bid": business_id},
        ), "duplicate entitlement must violate the unique constraint"
        # RESTRICT: the inviter cannot be deleted while referenced...
        assert _rejected("DELETE FROM users WHERE id = :uid", {"uid": user_id}), (
            "deleting a referenced inviter must be RESTRICTed"
        )
        # ...but after the invitation row is gone, user deletion CASCADES the
        # reset token (sessions-style lifecycle).
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM business_invitations"))
            connection.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
            remaining = connection.execute(
                text("SELECT count(*) FROM password_reset_tokens")
            ).scalar_one()
        assert remaining == 0, "reset tokens must CASCADE with their user"

        # Round trip with remaining data present (business + entitlement).
        command.downgrade(config, _M2C_ERA_REVISION)
        tables = set(inspect(engine).get_table_names())
        assert "business_invitations" not in tables
        assert "password_reset_tokens" not in tables
        assert "feature_entitlements" not in tables
        assert "businesses" in tables  # earlier schema untouched
        command.upgrade(config, "head")
        assert "feature_entitlements" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


# The M2D revision (down_revision of the M3A catalog migration).
_M2D_REVISION = "6fbce030db33"


def test_m3a_constraints_and_round_trip_with_real_rows(empty_database_url: str) -> None:
    """M3A catalog tables behave with real data (ADR-017).

    Exercises the case-insensitive expression uniques, the tenant-safe
    composite FKs (cross-tenant parents are database errors), the dietary
    canonical-lowercase CHECK, non-negative price/position CHECKs, and the
    DEFERRABLE position uniques (transient permutation inside one
    transaction, violation surfaced at commit); then proves the downgrade
    drops the three tables with earlier data intact and the chain
    re-applies. Scratch database only.
    """
    config = _config(empty_database_url)
    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.begin() as connection:
            business_a = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'A', 'biz-a', 'active') RETURNING id"
                )
            ).scalar_one()
            business_b = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'B', 'biz-b', 'active') RETURNING id"
                )
            ).scalar_one()
            category_a = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Curries', 0, true)"
                    " RETURNING id"
                ),
                {"bid": business_a},
            ).scalar_one()
            item_a = connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " VALUES (gen_random_uuid(), :bid, :cid, 'Samosa', 350, 0, true,"
                    " false, false) RETURNING id"
                ),
                {"bid": business_a, "cid": category_a},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO menu_item_dietary_tags (id, business_id, item_id, tag)"
                    " VALUES (gen_random_uuid(), :bid, :iid, 'halal')"
                ),
                {"bid": business_a, "iid": item_a},
            )

        def _rejected(statement: str, params: dict[str, object]) -> bool:
            # The whole transaction is inside the try: DEFERRED constraints
            # raise at commit (transaction exit), not at statement time.
            try:
                with engine.begin() as connection:
                    connection.execute(text(statement), params)
            except Exception:
                return True
            return False

        # Case-insensitive category-name unique per business.
        assert _rejected(
            "INSERT INTO menu_categories (id, business_id, name, position, is_visible)"
            " VALUES (gen_random_uuid(), :bid, 'CURRIES', 1, true)",
            {"bid": business_a},
        ), "case-variant duplicate category name must violate the expression index"
        # ...but the same name under another business is allowed.
        assert not _rejected(
            "INSERT INTO menu_categories (id, business_id, name, position, is_visible)"
            " VALUES (gen_random_uuid(), :bid, 'Curries', 0, true)",
            {"bid": business_b},
        )
        # Case-insensitive item-name unique per category.
        assert _rejected(
            "INSERT INTO menu_items (id, business_id, category_id, name, price_minor,"
            " position, is_available, is_hidden, is_featured) VALUES"
            " (gen_random_uuid(), :bid, :cid, 'SAMOSA', 350, 1, true, false, false)",
            {"bid": business_a, "cid": category_a},
        ), "case-variant duplicate item name in one category must violate"
        # Cross-tenant composite FK: business B cannot parent an item under
        # business A's category — the (business_id, category_id) pair fails.
        assert _rejected(
            "INSERT INTO menu_items (id, business_id, category_id, name, price_minor,"
            " position, is_available, is_hidden, is_featured) VALUES"
            " (gen_random_uuid(), :bid, :cid, 'Intruder', 100, 0, true, false, false)",
            {"bid": business_b, "cid": category_a},
        ), "cross-tenant item parenting must be a database error"
        # Cross-tenant composite FK: B cannot tag A's item.
        assert _rejected(
            "INSERT INTO menu_item_dietary_tags (id, business_id, item_id, tag)"
            " VALUES (gen_random_uuid(), :bid, :iid, 'vegan')",
            {"bid": business_b, "iid": item_a},
        ), "cross-tenant dietary tagging must be a database error"
        # Dietary canonical-lowercase CHECK.
        assert _rejected(
            "INSERT INTO menu_item_dietary_tags (id, business_id, item_id, tag)"
            " VALUES (gen_random_uuid(), :bid, :iid, 'Vegan')",
            {"bid": business_a, "iid": item_a},
        ), "non-canonical tag casing must violate the CHECK"
        # Non-negative price and position CHECKs.
        assert _rejected(
            "INSERT INTO menu_items (id, business_id, category_id, name, price_minor,"
            " position, is_available, is_hidden, is_featured) VALUES"
            " (gen_random_uuid(), :bid, :cid, 'Negative', -1, 1, true, false, false)",
            {"bid": business_a, "cid": category_a},
        ), "negative price must violate the CHECK"
        assert _rejected(
            "INSERT INTO menu_categories (id, business_id, name, position, is_visible)"
            " VALUES (gen_random_uuid(), :bid, 'Sweets', -1, true)",
            {"bid": business_a},
        ), "negative position must violate the CHECK"

        # DEFERRABLE position unique: a transient duplicate inside one
        # transaction is legal when resolved before commit...
        with engine.begin() as connection:
            second = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Sweets', 1, true)"
                    " RETURNING id"
                ),
                {"bid": business_a},
            ).scalar_one()
            connection.execute(
                text("UPDATE menu_categories SET position = 0 WHERE id = :cid"),
                {"cid": second},
            )  # transient duplicate with category_a's position 0
            connection.execute(
                text("UPDATE menu_categories SET position = 1 WHERE id = :cid"),
                {"cid": second},
            )  # resolved before commit
        # ...but an unresolved duplicate is rejected at commit.
        assert _rejected(
            "UPDATE menu_categories SET position = 0 WHERE id = :cid",
            {"cid": second},
        ), "an unresolved duplicate position must violate at commit"

        # Item deletion cascades its dietary tags.
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM menu_items WHERE id = :iid"), {"iid": item_a})
            remaining = connection.execute(
                text("SELECT count(*) FROM menu_item_dietary_tags")
            ).scalar_one()
        assert remaining == 0, "dietary tags must CASCADE with their item"

        # Round trip: downgrade drops the catalog tables, earlier data
        # survives, and the chain re-applies.
        command.downgrade(config, _M2D_REVISION)
        tables = set(inspect(engine).get_table_names())
        assert "menu_categories" not in tables
        assert "menu_items" not in tables
        assert "menu_item_dietary_tags" not in tables
        assert "businesses" in tables
        command.upgrade(config, "head")
        assert "menu_items" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
