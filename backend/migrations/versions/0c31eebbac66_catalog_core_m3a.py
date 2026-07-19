"""Catalog core (M3A, ADR-017).

Three tenant-owned tables:

* ``menu_categories`` — menu sections; dense DEFERRABLE-unique positions
  per business; case-insensitive name uniqueness per business (expression
  index, ruling R6); ``UNIQUE (business_id, id)`` as the composite-FK
  target.
* ``menu_items`` — sellable items; integer minor-unit ``price_minor`` with
  no currency column (currency is the business's, docs/03); separate
  ``is_available`` / ``is_hidden`` / ``is_featured`` states; tenant-safe
  composite FK to categories so a cross-tenant parent is a database error;
  dense DEFERRABLE-unique positions per category; case-insensitive name
  uniqueness per category; partial featured index for the R1 count guard.
* ``menu_item_dietary_tags`` — registry-validated tags (D6), stored
  canonical lowercase (CHECK); CASCADE with their item.

The downgrade drops the three tables (pre-launch operational state; audit
history lives in ``audit_events`` and is untouched). Development/scratch
operation only; production policy is forward-fix (blueprint §17.4).

Revision ID: 0c31eebbac66
Revises: 6fbce030db33
Create Date: 2026-07-19 16:08:34.840446
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0c31eebbac66"
down_revision: str | Sequence[str] | None = "6fbce030db33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "menu_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_menu_categories_name_length")
        ),
        sa.CheckConstraint(
            "description IS NULL OR char_length(description) <= 500",
            name=op.f("ck_menu_categories_description_length"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_menu_categories_position_nonnegative")),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_menu_categories_updated_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_menu_categories_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_menu_categories")),
        sa.UniqueConstraint("business_id", "id", name=op.f("uq_menu_categories_business_id_id")),
        sa.UniqueConstraint(
            "business_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name=op.f("uq_menu_categories_business_id_position"),
        ),
    )
    op.create_index(
        "uq_menu_categories_name_ci",
        "menu_categories",
        ["business_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "menu_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_menu_items_name_length")
        ),
        sa.CheckConstraint(
            "description IS NULL OR char_length(description) <= 1000",
            name=op.f("ck_menu_items_description_length"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_menu_items_position_nonnegative")),
        sa.CheckConstraint("price_minor >= 0", name=op.f("ck_menu_items_price_nonnegative")),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_menu_items_updated_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "category_id"],
            ["menu_categories.business_id", "menu_categories.id"],
            name=op.f("fk_menu_items_business_id_category_id_menu_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_menu_items_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_menu_items")),
        sa.UniqueConstraint(
            "business_id",
            "category_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name=op.f("uq_menu_items_business_id_category_id_position"),
        ),
        sa.UniqueConstraint("business_id", "id", name=op.f("uq_menu_items_business_id_id")),
    )
    op.create_index(
        "ix_menu_items_business_id_featured",
        "menu_items",
        ["business_id"],
        unique=False,
        postgresql_where=sa.text("is_featured"),
    )
    op.create_index(
        "uq_menu_items_name_ci",
        "menu_items",
        ["business_id", "category_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "menu_item_dietary_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("tag <> ''", name=op.f("ck_menu_item_dietary_tags_tag_not_empty")),
        sa.CheckConstraint(
            "tag = lower(btrim(tag))", name=op.f("ck_menu_item_dietary_tags_tag_canonical")
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "item_id"],
            ["menu_items.business_id", "menu_items.id"],
            name=op.f("fk_menu_item_dietary_tags_business_id_item_id_menu_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_menu_item_dietary_tags_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_menu_item_dietary_tags")),
        sa.UniqueConstraint(
            "business_id",
            "item_id",
            "tag",
            name=op.f("uq_menu_item_dietary_tags_business_id_item_id_tag"),
        ),
    )


def downgrade() -> None:
    # Reverse of creation (children first). Pre-launch operational state
    # only; audit history lives in audit_events and is untouched.
    op.drop_table("menu_item_dietary_tags")
    op.drop_index("uq_menu_items_name_ci", table_name="menu_items")
    op.drop_index(
        "ix_menu_items_business_id_featured",
        table_name="menu_items",
        postgresql_where=sa.text("is_featured"),
    )
    op.drop_table("menu_items")
    op.drop_index("uq_menu_categories_name_ci", table_name="menu_categories")
    op.drop_table("menu_categories")
