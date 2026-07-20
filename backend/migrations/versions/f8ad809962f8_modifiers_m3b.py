"""Modifiers (M3B, ADR-017).

Two tenant-owned tables:

* ``modifier_groups`` — per-item customization groups (ruling D10: one
  item, no cross-item library); DB-enforced selection numeric domain in
  three separately named CHECKs (min 0-30; max NULL or 1-30; min ≤ max);
  DEFERRABLE dense-position unique per item; case-insensitive name
  uniqueness per item; ``UNIQUE (business_id, id)`` as the option
  composite-FK target; groups CASCADE with their item.
* ``modifier_options`` — per-group options; price delta bounded
  0..10,000,000 by named CHECKs (shares the F1 catalog price bound);
  ``is_available`` operator toggle (feeds computed satisfiability);
  DEFERRABLE dense-position unique per group; case-insensitive name
  uniqueness per group; options CASCADE with their group. Deliberately
  no ``UNIQUE (business_id, id)`` — nothing references options.

Value columns carry application-side defaults only (server defaults on
timestamps alone), so direct SQL omitting a value fails explicitly.
The downgrade drops both tables (dev/scratch only; production policy is
forward-fix, blueprint §17.4).

Revision ID: f8ad809962f8
Revises: 0c31eebbac66
Create Date: 2026-07-19 23:37:04.453210
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8ad809962f8"
down_revision: str | Sequence[str] | None = "0c31eebbac66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "modifier_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("min_select", sa.Integer(), nullable=False),
        sa.Column("max_select", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
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
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_modifier_groups_name_length")
        ),
        sa.CheckConstraint(
            "max_select IS NULL OR (max_select >= 1 AND max_select <= 30)",
            name=op.f("ck_modifier_groups_max_select_range"),
        ),
        sa.CheckConstraint(
            "max_select IS NULL OR min_select <= max_select",
            name=op.f("ck_modifier_groups_min_le_max"),
        ),
        sa.CheckConstraint(
            "min_select >= 0 AND min_select <= 30", name=op.f("ck_modifier_groups_min_select_range")
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_modifier_groups_position_nonnegative")),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_modifier_groups_updated_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "item_id"],
            ["menu_items.business_id", "menu_items.id"],
            name=op.f("fk_modifier_groups_business_id_item_id_menu_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_modifier_groups_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modifier_groups")),
        sa.UniqueConstraint("business_id", "id", name=op.f("uq_modifier_groups_business_id_id")),
        sa.UniqueConstraint(
            "business_id",
            "item_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name=op.f("uq_modifier_groups_business_id_item_id_position"),
        ),
    )
    op.create_index(
        "uq_modifier_groups_name_ci",
        "modifier_groups",
        ["business_id", "item_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "modifier_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price_delta_minor", sa.Integer(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
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
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_modifier_options_name_length")
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_modifier_options_position_nonnegative")),
        sa.CheckConstraint(
            "price_delta_minor <= 10000000", name=op.f("ck_modifier_options_price_delta_maximum")
        ),
        sa.CheckConstraint(
            "price_delta_minor >= 0", name=op.f("ck_modifier_options_price_delta_nonnegative")
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_modifier_options_updated_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "group_id"],
            ["modifier_groups.business_id", "modifier_groups.id"],
            name=op.f("fk_modifier_options_business_id_group_id_modifier_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_modifier_options_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modifier_options")),
        sa.UniqueConstraint(
            "business_id",
            "group_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name=op.f("uq_modifier_options_business_id_group_id_position"),
        ),
    )
    op.create_index(
        "uq_modifier_options_name_ci",
        "modifier_options",
        ["business_id", "group_id", sa.literal_column("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    # Exact reverse of creation (children first). Dev/scratch only;
    # production policy is forward-fix.
    op.drop_index("uq_modifier_options_name_ci", table_name="modifier_options")
    op.drop_table("modifier_options")
    op.drop_index("uq_modifier_groups_name_ci", table_name="modifier_groups")
    op.drop_table("modifier_groups")
