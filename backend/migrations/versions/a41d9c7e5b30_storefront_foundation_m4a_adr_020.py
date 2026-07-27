"""Storefront foundation (M4A, ADR-020).

One additive tenant-owned table, ``storefront_versions``, holding every
draft, published, and archived composition of every business
(blueprint §7.4). Nothing existing is altered: no ``businesses`` column, no
media-schema change, no backfill, and no rewrite of any M3 row.

Invariants carried by the schema rather than by convention:

* two partial unique indexes give the blueprint §9.2 singletons — at most
  one ``draft`` and at most one ``published`` version per business;
* ``version_number`` is minted at publication, so the paired CHECK ties
  "is a draft" to "has no number" in both directions;
* publication timestamp and actor arrive together, and only on a
  non-draft row;
* ``UNIQUE (business_id, id)`` backs the tenant-safe composite self
  foreign key, so a version's provenance can never point at another
  tenant's version;
* ``config`` is a JSON object, the integrity boundary behind the section
  registry for any path that is not the application.

The composite self-FK is named explicitly: the naming convention would
generate a 70-character identifier and PostgreSQL truncates at 63 bytes,
which would leave the model and the database disagreeing about its name.

Value columns carry application-side defaults only (server defaults on
timestamps alone), matching M3. The downgrade drops only this table
(dev/scratch only; production policy is forward-fix, blueprint §17.4).

Revision ID: a41d9c7e5b30
Revises: 59b463781dcc
Create Date: 2026-07-26 09:41:12.883104
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a41d9c7e5b30"
down_revision: str | Sequence[str] | None = "59b463781dcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "storefront_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("design_variant", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(published_at IS NULL) = (published_by_user_id IS NULL)",
            name=op.f("ck_storefront_versions_publication_pairing"),
        ),
        sa.CheckConstraint(
            "(state = 'draft') = (published_at IS NULL)",
            name=op.f("ck_storefront_versions_draft_not_published"),
        ),
        sa.CheckConstraint(
            "(state = 'draft') = (version_number IS NULL)",
            name=op.f("ck_storefront_versions_draft_has_no_version_number"),
        ),
        sa.CheckConstraint(
            "design_variant <> ''",
            name=op.f("ck_storefront_versions_design_variant_not_empty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(config) = 'object'",
            name=op.f("ck_storefront_versions_config_is_object"),
        ),
        sa.CheckConstraint(
            "lock_version >= 0",
            name=op.f("ck_storefront_versions_lock_version_nonnegative"),
        ),
        sa.CheckConstraint(
            "schema_version > 0",
            name=op.f("ck_storefront_versions_schema_version_positive"),
        ),
        sa.CheckConstraint(
            "source_version_id IS NULL OR source_version_id <> id",
            name=op.f("ck_storefront_versions_source_not_self"),
        ),
        sa.CheckConstraint(
            "state IN ('draft', 'published', 'archived')",
            name=op.f("ck_storefront_versions_state_valid"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_storefront_versions_updated_after_creation"),
        ),
        sa.CheckConstraint(
            "version_number IS NULL OR version_number > 0",
            name=op.f("ck_storefront_versions_version_number_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "source_version_id"],
            ["storefront_versions.business_id", "storefront_versions.id"],
            name="fk_storefront_versions_source_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_storefront_versions_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"],
            ["users.id"],
            name=op.f("fk_storefront_versions_published_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storefront_versions")),
        sa.UniqueConstraint(
            "business_id", "id", name=op.f("uq_storefront_versions_business_id_id")
        ),
    )
    op.create_index(
        "ix_storefront_versions_business_id_state",
        "storefront_versions",
        ["business_id", "state"],
        unique=False,
    )
    op.create_index(
        "uq_storefront_versions_business_id_version_number",
        "storefront_versions",
        ["business_id", "version_number"],
        unique=True,
        postgresql_where=sa.text("version_number IS NOT NULL"),
    )
    op.create_index(
        "uq_storefront_versions_one_draft",
        "storefront_versions",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("state = 'draft'"),
    )
    op.create_index(
        "uq_storefront_versions_one_published",
        "storefront_versions",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("state = 'published'"),
    )


def downgrade() -> None:
    # Drops only what this revision added; every M3 table and row is
    # untouched. Dev/scratch only — production policy is forward-fix.
    op.drop_index(
        "uq_storefront_versions_one_published",
        table_name="storefront_versions",
        postgresql_where=sa.text("state = 'published'"),
    )
    op.drop_index(
        "uq_storefront_versions_one_draft",
        table_name="storefront_versions",
        postgresql_where=sa.text("state = 'draft'"),
    )
    op.drop_index(
        "uq_storefront_versions_business_id_version_number",
        table_name="storefront_versions",
        postgresql_where=sa.text("version_number IS NOT NULL"),
    )
    op.drop_index(
        "ix_storefront_versions_business_id_state",
        table_name="storefront_versions",
    )
    op.drop_table("storefront_versions")
