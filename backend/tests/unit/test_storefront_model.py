"""Storefront persistence metadata (M4A, ADR-020).

Schema-level assertions that need no database: the invariants the M4B
service will rely on are expressed as named constraints, and every
generated identifier fits PostgreSQL's limit. Behavior against real rows —
the singletons, the tenant-safe provenance FK, the CHECKs — is proved in
tests/integration/test_migrations.py.
"""

from typing import cast

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Table, UniqueConstraint

from app.core.database import Base
from app.domains.storefront.models import StorefrontVersion, VersionState

# Declarative types ``__table__`` as ``FromClause``; the concrete ``Table``
# is what carries ``constraints`` and ``indexes``.
_TABLE = cast(Table, StorefrontVersion.__table__)

# PostgreSQL truncates identifiers at 63 bytes. A generated name longer
# than that would leave the model and the database silently disagreeing
# about a constraint's name, which breaks every by-name assertion and any
# migration that later drops it.
_MAX_IDENTIFIER_BYTES = 63


def test_version_states_are_the_three_lifecycle_values() -> None:
    assert {state.value for state in VersionState} == {"draft", "published", "archived"}


def test_the_table_is_tenant_owned() -> None:
    table = _TABLE
    assert table.name == "storefront_versions"
    assert "business_id" in table.c
    assert not table.c.business_id.nullable


def test_named_checks_express_the_version_invariants() -> None:
    names = {
        constraint.name
        for constraint in _TABLE.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert names == {
        "ck_storefront_versions_state_valid",
        "ck_storefront_versions_version_number_positive",
        "ck_storefront_versions_draft_has_no_version_number",
        "ck_storefront_versions_lock_version_nonnegative",
        "ck_storefront_versions_schema_version_positive",
        "ck_storefront_versions_source_not_self",
        "ck_storefront_versions_design_variant_not_empty",
        "ck_storefront_versions_publication_pairing",
        "ck_storefront_versions_draft_not_published",
        "ck_storefront_versions_updated_after_creation",
        "ck_storefront_versions_config_is_object",
    }


def test_the_two_singleton_indexes_are_partial_and_unique() -> None:
    """Blueprint §9.2: one draft and at most one published, per business."""
    indexes = {str(index.name): index for index in _TABLE.indexes}

    for name, predicate in (
        ("uq_storefront_versions_one_draft", "state = 'draft'"),
        ("uq_storefront_versions_one_published", "state = 'published'"),
    ):
        index = indexes[name]
        assert index.unique
        assert str(index.dialect_options["postgresql"]["where"]) == predicate


def test_version_numbers_are_unique_per_business_where_present() -> None:
    index = {str(index.name): index for index in _TABLE.indexes}[
        "uq_storefront_versions_business_id_version_number"
    ]
    assert index.unique
    assert str(index.dialect_options["postgresql"]["where"]) == "version_number IS NOT NULL"


def test_provenance_is_a_tenant_safe_composite_self_reference() -> None:
    """A version can only ever be seeded or restored from its own business."""
    composite = [
        constraint
        for constraint in _TABLE.constraints
        if isinstance(constraint, ForeignKeyConstraint) and len(constraint.elements) == 2
    ]
    assert len(composite) == 1
    constraint = composite[0]
    assert constraint.name == "fk_storefront_versions_source_version"
    assert [element.column.table.name for element in constraint.elements] == [
        "storefront_versions",
        "storefront_versions",
    ]
    assert {element.column.name for element in constraint.elements} == {"business_id", "id"}
    assert constraint.ondelete == "RESTRICT"

    # ...backed by the unique key it references.
    unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in _TABLE.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("business_id", "id") in unique


def test_every_generated_identifier_fits_postgresql() -> None:
    """Guards the whole schema, not only storefront.

    Found while naming the composite self-FK: the convention would have
    generated a 70-character identifier, and PostgreSQL would have
    truncated it without complaint.
    """
    oversized: list[str] = []
    for table in Base.metadata.tables.values():
        names = [constraint.name for constraint in table.constraints]
        names += [index.name for index in table.indexes]
        oversized += [
            str(name)
            for name in names
            if name is not None and len(str(name).encode()) > _MAX_IDENTIFIER_BYTES
        ]
    assert oversized == []
