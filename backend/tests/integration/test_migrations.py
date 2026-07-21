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
        # entitlements + M3A catalog core + M3B modifiers + M3C media.
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
            "modifier_groups",
            "modifier_options",
            "media_assets",
            "media_asset_variants",
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
    from app.domains.media import models as _media_models  # noqa: F401

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
        # Price-range CHECKs (F1 ruling: 0 <= price_minor <= 10,000,000).
        assert _rejected(
            "INSERT INTO menu_items (id, business_id, category_id, name, price_minor,"
            " position, is_available, is_hidden, is_featured) VALUES"
            " (gen_random_uuid(), :bid, :cid, 'Negative', -1, 1, true, false, false)",
            {"bid": business_a, "cid": category_a},
        ), "negative price must violate the CHECK"
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO menu_items (id, business_id, category_id, name,"
                        " price_minor, position, is_available, is_hidden, is_featured)"
                        " VALUES (gen_random_uuid(), :bid, :cid, 'Too Expensive',"
                        " 10000001, 1, true, false, false)"
                    ),
                    {"bid": business_a, "cid": category_a},
                )
            raise AssertionError("price above the approved maximum must be rejected")
        except AssertionError:
            raise
        except Exception as exc:
            assert "ck_menu_items_price_maximum" in str(exc), (
                "the named price_maximum CHECK must be the violated constraint"
            )
        # The exact maximum is storable.
        assert not _rejected(
            "INSERT INTO menu_items (id, business_id, category_id, name, price_minor,"
            " position, is_available, is_hidden, is_featured) VALUES"
            " (gen_random_uuid(), :bid, :cid, 'Banquet Package', 10000000, 1, true,"
            " false, false)",
            {"bid": business_a, "cid": category_a},
        ), "the exact approved maximum price must be storable"
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


# The M3A revision (down_revision of the M3B modifiers migration).
_M3A_REVISION = "0c31eebbac66"


def test_m3b_constraints_and_round_trip_with_real_rows(empty_database_url: str) -> None:
    """M3B modifier tables behave with real data (ADR-017).

    Exercises the named selection-domain CHECKs (the five mandated
    direct-SQL rejections), the price-delta range CHECKs, cross-tenant
    composite-FK rejections for both child tables, case-insensitive
    uniques, DEFERRABLE position behavior, the item->group->option and
    group->option cascades, and the fail-explicit NOT NULL value columns;
    then proves the downgrade drops both tables with earlier data intact
    and the chain re-applies. Scratch database only.
    """
    config = _config(empty_database_url)
    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.begin() as connection:
            business_a = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'A', 'mod-a', 'active') RETURNING id"
                )
            ).scalar_one()
            business_b = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'B', 'mod-b', 'active') RETURNING id"
                )
            ).scalar_one()
            category_a = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Mains', 0, true)"
                    " RETURNING id"
                ),
                {"bid": business_a},
            ).scalar_one()
            item_a = connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " VALUES (gen_random_uuid(), :bid, :cid, 'Curry', 1200, 0, true,"
                    " false, false) RETURNING id"
                ),
                {"bid": business_a, "cid": category_a},
            ).scalar_one()
            group_a = connection.execute(
                text(
                    "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                    " min_select, max_select, position) VALUES (gen_random_uuid(),"
                    " :bid, :iid, 'Spice Level', 1, 1, 0) RETURNING id"
                ),
                {"bid": business_a, "iid": item_a},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO modifier_options (id, business_id, group_id, name,"
                    " price_delta_minor, is_available, position) VALUES"
                    " (gen_random_uuid(), :bid, :gid, 'Mild', 0, true, 0)"
                ),
                {"bid": business_a, "gid": group_a},
            )

        def _rejected_with(statement: str, params: dict[str, object], fragment: str) -> None:
            try:
                with engine.begin() as connection:
                    connection.execute(text(statement), params)
            except Exception as exc:
                assert fragment in str(exc), (
                    f"expected {fragment!r} to be the violated constraint, got: {exc}"
                )
                return
            raise AssertionError(f"statement must be rejected by {fragment!r}")

        group_insert = (
            "INSERT INTO modifier_groups (id, business_id, item_id, name,"
            " min_select, max_select, position) VALUES (gen_random_uuid(), :bid,"
            " :iid, :name, :mn, :mx, :pos)"
        )
        # The five mandated selection-domain rejections, each by its named CHECK.
        _rejected_with(
            group_insert,
            {"bid": business_a, "iid": item_a, "name": "Bad1", "mn": 31, "mx": None, "pos": 1},
            "ck_modifier_groups_min_select_range",
        )
        _rejected_with(
            group_insert,
            {"bid": business_a, "iid": item_a, "name": "Bad2", "mn": 0, "mx": 31, "pos": 1},
            "ck_modifier_groups_max_select_range",
        )
        _rejected_with(
            group_insert,
            {"bid": business_a, "iid": item_a, "name": "Bad3", "mn": -1, "mx": None, "pos": 1},
            "ck_modifier_groups_min_select_range",
        )
        _rejected_with(
            group_insert,
            {"bid": business_a, "iid": item_a, "name": "Bad4", "mn": 0, "mx": 0, "pos": 1},
            "ck_modifier_groups_max_select_range",
        )
        _rejected_with(
            group_insert,
            {"bid": business_a, "iid": item_a, "name": "Bad5", "mn": 5, "mx": 4, "pos": 1},
            "ck_modifier_groups_min_le_max",
        )

        option_insert = (
            "INSERT INTO modifier_options (id, business_id, group_id, name,"
            " price_delta_minor, is_available, position) VALUES (gen_random_uuid(),"
            " :bid, :gid, :name, :delta, true, :pos)"
        )
        # Price-delta range (F1/D1): negative and above-maximum rejected by name.
        _rejected_with(
            option_insert,
            {"bid": business_a, "gid": group_a, "name": "Neg", "delta": -1, "pos": 1},
            "ck_modifier_options_price_delta_nonnegative",
        )
        _rejected_with(
            option_insert,
            {"bid": business_a, "gid": group_a, "name": "Huge", "delta": 10000001, "pos": 1},
            "ck_modifier_options_price_delta_maximum",
        )
        # The exact maximum is storable.
        with engine.begin() as connection:
            connection.execute(
                text(option_insert),
                {"bid": business_a, "gid": group_a, "name": "Banquet", "delta": 10000000, "pos": 1},
            )

        # Fail-explicit defaults: omitting a NOT NULL value column fails
        # rather than silently acquiring a divergent default.
        _rejected_with(
            "INSERT INTO modifier_options (id, business_id, group_id, name,"
            " price_delta_minor, position) VALUES (gen_random_uuid(), :bid, :gid,"
            " 'NoAvail', 0, 2)",
            {"bid": business_a, "gid": group_a},
            "is_available",
        )

        # Cross-tenant composite FKs: B cannot parent a group under A's item,
        # nor an option under A's group.
        _rejected_with(
            group_insert,
            {"bid": business_b, "iid": item_a, "name": "Intruder", "mn": 0, "mx": None, "pos": 0},
            "fk_modifier_groups_business_id_item_id_menu_items",
        )
        _rejected_with(
            option_insert,
            {"bid": business_b, "gid": group_a, "name": "Intruder", "delta": 0, "pos": 0},
            "fk_modifier_options_business_id_group_id_modifier_groups",
        )

        # Case-insensitive uniques within the parent scope.
        _rejected_with(
            group_insert,
            {
                "bid": business_a,
                "iid": item_a,
                "name": "SPICE LEVEL",
                "mn": 0,
                "mx": None,
                "pos": 1,
            },
            "uq_modifier_groups_name_ci",
        )
        _rejected_with(
            option_insert,
            {"bid": business_a, "gid": group_a, "name": "MILD", "delta": 0, "pos": 2},
            "uq_modifier_options_name_ci",
        )

        # DEFERRABLE position unique: transient duplicate inside one
        # transaction is legal when resolved; unresolved fails at commit.
        with engine.begin() as connection:
            second = connection.execute(
                text(group_insert + " RETURNING id"),
                {
                    "bid": business_a,
                    "iid": item_a,
                    "name": "Add-ons",
                    "mn": 0,
                    "mx": None,
                    "pos": 1,
                },
            ).scalar_one()
            connection.execute(
                text("UPDATE modifier_groups SET position = 0 WHERE id = :gid"),
                {"gid": second},
            )
            connection.execute(
                text("UPDATE modifier_groups SET position = 1 WHERE id = :gid"),
                {"gid": second},
            )
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE modifier_groups SET position = 0 WHERE id = :gid"),
                    {"gid": second},
                )
            raise AssertionError("unresolved duplicate group position must fail at commit")
        except AssertionError:
            raise
        except Exception as exc:
            assert "uq_modifier_groups_business_id_item_id_position" in str(exc)

        # Cascade chains: group -> options; then item -> groups -> options.
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM modifier_groups WHERE id = :gid"), {"gid": second})
            connection.execute(text("DELETE FROM menu_items WHERE id = :iid"), {"iid": item_a})
            groups_left = connection.execute(
                text("SELECT count(*) FROM modifier_groups")
            ).scalar_one()
            options_left = connection.execute(
                text("SELECT count(*) FROM modifier_options")
            ).scalar_one()
        assert groups_left == 0, "groups must CASCADE with their item"
        assert options_left == 0, "options must CASCADE with their group/item"

        # Round trip: downgrade drops both tables, earlier data survives,
        # and the chain re-applies.
        command.downgrade(config, _M3A_REVISION)
        tables = set(inspect(engine).get_table_names())
        assert "modifier_groups" not in tables
        assert "modifier_options" not in tables
        assert "menu_categories" in tables
        command.upgrade(config, "head")
        assert "modifier_options" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


# The M3B revision (down_revision of the M3C media migration).
_M3B_REVISION = "f8ad809962f8"

_SHA_OK = "0" * 63 + "a"


def test_m3c_constraints_and_round_trip_with_real_rows(empty_database_url: str) -> None:
    """M3C media tables behave with real data (ADR-017).

    Exercises the kind/status/pairing/format/range CHECKs, the checksum
    shape CHECK, the cross-tenant composite FKs for variants and the
    menu-item attachment, the RESTRICT protecting referenced assets, the
    alt-requires-image pairing, the asset->variant cascade, and the
    fail-explicit NOT NULL value columns; then proves the downgrade
    drops the attachment and both tables with earlier data intact and
    the chain re-applies. Scratch database only.
    """
    config = _config(empty_database_url)
    command.upgrade(config, "head")

    engine = create_engine(empty_database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.begin() as connection:
            business_a = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'A', 'med-a', 'active') RETURNING id"
                )
            ).scalar_one()
            business_b = connection.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) VALUES"
                    " (gen_random_uuid(), 'B', 'med-b', 'active') RETURNING id"
                )
            ).scalar_one()
            category_a = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Mains', 0, true)"
                    " RETURNING id"
                ),
                {"bid": business_a},
            ).scalar_one()
            item_a = connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " VALUES (gen_random_uuid(), :bid, :cid, 'Kacchi', 1500, 0, true,"
                    " false, false) RETURNING id"
                ),
                {"bid": business_a, "cid": category_a},
            ).scalar_one()
            asset_a = connection.execute(
                text(
                    "INSERT INTO media_assets (id, business_id, kind, status,"
                    " pending_expires_at, original_filename, declared_content_type,"
                    " source_format, width, height, byte_size, checksum_sha256)"
                    " VALUES (gen_random_uuid(), :bid, 'image', 'pending',"
                    " now() + interval '48 hours', 'kacchi.jpg', 'image/jpeg',"
                    " 'jpeg', 1600, 1200, 123456, :sha) RETURNING id"
                ),
                {"bid": business_a, "sha": _SHA_OK},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO media_asset_variants (id, business_id, asset_id,"
                    " variant, width, height, byte_size, checksum_sha256) VALUES"
                    " (gen_random_uuid(), :bid, :aid, 'w320', 320, 240, 4567, :sha)"
                ),
                {"bid": business_a, "aid": asset_a, "sha": _SHA_OK},
            )

        def _rejected_with(statement: str, params: dict[str, object], fragment: str) -> None:
            try:
                with engine.begin() as connection:
                    connection.execute(text(statement), params)
            except Exception as exc:
                assert fragment in str(exc), (
                    f"expected {fragment!r} to be the violated constraint, got: {exc}"
                )
                return
            raise AssertionError(f"statement must be rejected by {fragment!r}")

        asset_insert = (
            "INSERT INTO media_assets (id, business_id, kind, status,"
            " pending_expires_at, original_filename, declared_content_type,"
            " source_format, width, height, byte_size, checksum_sha256) VALUES"
            " (gen_random_uuid(), :bid, :kind, :status, :exp, :fname, :ctype,"
            " :fmt, :w, :h, :bytes, :sha)"
        )
        base = {
            "bid": business_a,
            "kind": "image",
            "status": "active",
            "exp": None,
            "fname": "ok.png",
            "ctype": "image/png",
            "fmt": "png",
            "w": 100,
            "h": 100,
            "bytes": 1000,
            "sha": _SHA_OK,
        }
        # Closed-set CHECKs, each rejected by its named constraint.
        _rejected_with(asset_insert, {**base, "kind": "video"}, "ck_media_assets_kind_known")
        _rejected_with(asset_insert, {**base, "status": "failed"}, "ck_media_assets_status_known")
        _rejected_with(asset_insert, {**base, "fmt": "gif"}, "ck_media_assets_source_format_known")
        # Pairing CHECK: pending requires an expiry; active forbids one.
        _rejected_with(
            asset_insert,
            {**base, "status": "pending"},
            "ck_media_assets_pending_expiry_pairing",
        )
        with engine.begin() as connection:  # active + expiry also violates
            try:
                connection.execute(
                    text(asset_insert.replace(":exp", "now() + interval '1 hour'")),
                    {k: v for k, v in base.items() if k != "exp"},
                )
                raise AssertionError("active asset with an expiry must be rejected")
            except AssertionError:
                raise
            except Exception as exc:
                assert "ck_media_assets_pending_expiry_pairing" in str(exc)
        # Checksum shape: raw/uppercase/short values are unstorable.
        _rejected_with(asset_insert, {**base, "sha": "RAW" * 21 + "X"}, "ck_media_assets_checksum")
        _rejected_with(asset_insert, {**base, "sha": "a" * 63}, "ck_media_assets_checksum")
        # Dimension and byte bounds.
        _rejected_with(asset_insert, {**base, "w": 2561}, "ck_media_assets_width_range")
        _rejected_with(asset_insert, {**base, "h": 0}, "ck_media_assets_height_range")
        _rejected_with(asset_insert, {**base, "bytes": 0}, "ck_media_assets_byte_size_positive")
        # Fail-explicit defaults: omitting a NOT NULL value column fails.
        _rejected_with(
            "INSERT INTO media_assets (id, business_id, status, pending_expires_at,"
            " original_filename, declared_content_type, source_format, width,"
            " height, byte_size, checksum_sha256) VALUES (gen_random_uuid(), :bid,"
            " 'active', NULL, 'x.png', 'image/png', 'png', 10, 10, 10, :sha)",
            {"bid": business_a, "sha": _SHA_OK},
            "kind",
        )

        variant_insert = (
            "INSERT INTO media_asset_variants (id, business_id, asset_id, variant,"
            " width, height, byte_size, checksum_sha256) VALUES (gen_random_uuid(),"
            " :bid, :aid, :variant, :w, :h, :bytes, :sha)"
        )
        vbase = {
            "bid": business_a,
            "aid": asset_a,
            "variant": "w640",
            "w": 640,
            "h": 480,
            "bytes": 9000,
            "sha": _SHA_OK,
        }
        _rejected_with(
            variant_insert,
            {**vbase, "variant": "w2000"},
            "ck_media_asset_variants_variant_known",
        )
        # One row per logical variant.
        _rejected_with(
            variant_insert,
            {**vbase, "variant": "w320"},
            "uq_media_asset_variants_business_id_asset_id_variant",
        )
        # Cross-tenant composite FK: B cannot hang a variant on A's asset.
        _rejected_with(
            variant_insert,
            {**vbase, "bid": business_b},
            "fk_media_asset_variants_business_id_asset_id_media_assets",
        )

        # Attachment: same-tenant reference succeeds.
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE menu_items SET image_media_id = :aid WHERE id = :iid"),
                {"aid": asset_a, "iid": item_a},
            )
        item_b = None
        with engine.begin() as connection:
            category_b = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Mains', 0, true)"
                    " RETURNING id"
                ),
                {"bid": business_b},
            ).scalar_one()
            item_b = connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " VALUES (gen_random_uuid(), :bid, :cid, 'Borrowed', 900, 0,"
                    " true, false, false) RETURNING id"
                ),
                {"bid": business_b, "cid": category_b},
            ).scalar_one()
        _rejected_with(
            "UPDATE menu_items SET image_media_id = :aid WHERE id = :iid",
            {"aid": asset_a, "iid": item_b},
            "fk_menu_items_business_id_image_media_id_media_assets",
        )
        # Alt requires image; alt is bounded at 300.
        _rejected_with(
            "UPDATE menu_items SET image_alt_text = 'alone' WHERE id = :iid",
            {"iid": item_b},
            "ck_menu_items_image_alt_requires_image",
        )
        _rejected_with(
            "UPDATE menu_items SET image_alt_text = :alt WHERE id = :iid",
            {"alt": "x" * 301, "iid": item_a},
            "ck_menu_items_image_alt_text_length",
        )
        # RESTRICT: a referenced asset cannot be deleted...
        _rejected_with(
            "DELETE FROM media_assets WHERE id = :aid",
            {"aid": asset_a},
            "fk_menu_items_business_id_image_media_id_media_assets",
        )
        # ...but after clearing the reference, deletion cascades variants.
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE menu_items SET image_media_id = NULL WHERE id = :iid"),
                {"iid": item_a},
            )
            connection.execute(text("DELETE FROM media_assets WHERE id = :aid"), {"aid": asset_a})
            variants_left = connection.execute(
                text("SELECT count(*) FROM media_asset_variants")
            ).scalar_one()
        assert variants_left == 0, "variants must CASCADE with their asset"

        # Round trip: downgrade drops the attachment and both tables,
        # earlier data survives, and the chain re-applies.
        command.downgrade(config, _M3B_REVISION)
        tables = set(inspect(engine).get_table_names())
        assert "media_assets" not in tables
        assert "media_asset_variants" not in tables
        assert "menu_items" in tables
        item_columns = {col["name"] for col in inspect(engine).get_columns("menu_items")}
        assert "image_media_id" not in item_columns
        assert "image_alt_text" not in item_columns
        command.upgrade(config, "head")
        assert "media_asset_variants" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
