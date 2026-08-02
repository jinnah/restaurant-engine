"""Orders, idempotency, and the transactional outbox (M6A, ADR-026).

Adds the blueprint §9 order tables — ``orders``, ``order_lines``,
``order_line_options``, ``order_status_events`` — plus ``idempotency_keys``
(ruling D2) and the platform-global ``outbox_messages`` (ruling D14), and
one nullable column on ``fulfillment_settings``: ``max_orders_per_slot``
(ruling D3 — the per-slot throttle setting hours owns and the orders
checkout enforces; NULL means unlimited, so existing rows gain no cap).

What the schema carries: tenant-leading uniques and composite tenant-safe
child FKs (docs/04); the closed status/pickup/actor vocabularies as
CHECKs; the §9.2 invariants — totals components agree at creation, one
idempotency key per (business, operation), at most one outbox message per
(topic, order); and the D6/D7 present-but-frozen columns (``tax_minor``,
``discount_total_minor``, ``applied_promotions`` CHECKed to zero/empty)
so every historical snapshot already carries what later milestones
populate. Snapshots deliberately reference catalog by **bare provenance
UUIDs with no FK** (ruling D1): deleting a menu item referenced by an
order snapshot stays safe (blueprint §7.3).

What stays service-enforced: cart validation and pricing, slot validity,
the throttle count, order numbering under the Business row lock, and the
M6-producible status subset (the full §7.7 vocabulary is stored so M7
widens behavior without a schema change).

Additive only: nothing existing is altered beyond the one nullable
fulfillment column; no backfill. ``downgrade`` drops only what this
revision added and exists for development and scratch databases —
production policy is forward-fix (blueprint §17.4).

Revision ID: e7a2c94d51b8
Revises: c3d8f5a21e47
Create Date: 2026-08-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e7a2c94d51b8"
down_revision = "c3d8f5a21e47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fulfillment_settings",
        sa.Column("max_orders_per_slot", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_fulfillment_settings_max_orders_per_slot_bounds"),
        "fulfillment_settings",
        "max_orders_per_slot IS NULL OR max_orders_per_slot BETWEEN 1 AND 100",
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.Integer(), nullable=False),
        sa.Column("tracking_token_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_timezone", sa.Text(), nullable=False),
        sa.Column("customer_name", sa.Text(), nullable=False),
        sa.Column("customer_phone", sa.Text(), nullable=False),
        sa.Column("customer_email", sa.Text(), nullable=True),
        sa.Column("order_instructions", sa.Text(), nullable=True),
        sa.Column("consent_updates", sa.Boolean(), nullable=False),
        sa.Column("consent_marketing", sa.Boolean(), nullable=False),
        sa.Column("pickup_kind", sa.Text(), nullable=False),
        sa.Column("promised_pickup_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_minor", sa.BigInteger(), nullable=False),
        sa.Column("tax_minor", sa.BigInteger(), nullable=False),
        sa.Column("discount_total_minor", sa.BigInteger(), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("applied_promotions", JSONB(), nullable=False),
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
            "status IN ('submitted', 'accepted', 'preparing', 'ready',"
            " 'completed', 'rejected', 'cancelled')",
            name=op.f("ck_orders_status_known"),
        ),
        sa.CheckConstraint(
            "pickup_kind IN ('asap', 'scheduled')", name=op.f("ck_orders_pickup_kind_known")
        ),
        sa.CheckConstraint("order_number >= 1", name=op.f("ck_orders_order_number_positive")),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_orders_currency_iso4217_shape")
        ),
        sa.CheckConstraint("subtotal_minor >= 0", name=op.f("ck_orders_subtotal_nonnegative")),
        sa.CheckConstraint("total_minor >= 0", name=op.f("ck_orders_total_nonnegative")),
        sa.CheckConstraint("tax_minor = 0", name=op.f("ck_orders_tax_frozen_m6")),
        sa.CheckConstraint("discount_total_minor = 0", name=op.f("ck_orders_discount_frozen_m6")),
        sa.CheckConstraint(
            "applied_promotions = '[]'::jsonb", name=op.f("ck_orders_promotions_frozen_m6")
        ),
        sa.CheckConstraint(
            "total_minor = subtotal_minor + tax_minor - discount_total_minor",
            name=op.f("ck_orders_total_components_agree"),
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "id"),
        sa.UniqueConstraint("business_id", "order_number"),
        sa.UniqueConstraint("tracking_token_digest"),
    )
    op.create_index("ix_orders_business_placed", "orders", ["business_id", "placed_at"])
    op.create_index("ix_orders_business_promised", "orders", ["business_id", "promised_pickup_at"])

    op.create_table(
        "order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("item_provenance_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("base_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("item_instructions", sa.Text(), nullable=True),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 50", name=op.f("ck_order_lines_quantity_bounds")
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_order_lines_position_nonnegative")),
        sa.CheckConstraint(
            "base_price_minor >= 0", name=op.f("ck_order_lines_base_price_nonnegative")
        ),
        sa.CheckConstraint(
            "line_total_minor >= 0", name=op.f("ck_order_lines_line_total_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "order_id"],
            ["orders.business_id", "orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "id"),
        sa.UniqueConstraint("business_id", "order_id", "position"),
    )

    op.create_table(
        "order_line_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("group_provenance_id", sa.Uuid(), nullable=False),
        sa.Column("option_provenance_id", sa.Uuid(), nullable=False),
        sa.Column("group_display_name", sa.Text(), nullable=False),
        sa.Column("option_display_name", sa.Text(), nullable=False),
        sa.Column("price_delta_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_order_line_options_position_nonnegative")
        ),
        sa.CheckConstraint(
            "price_delta_minor >= 0",
            name=op.f("ck_order_line_options_price_delta_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "line_id"],
            ["order_lines.business_id", "order_lines.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "line_id", "position"),
    )

    op.create_table(
        "order_status_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor_kind", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_kind IN ('customer', 'member', 'system')",
            name=op.f("ck_order_status_events_actor_kind_known"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "order_id"],
            ["orders.business_id", "orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_status_events_order",
        "order_status_events",
        ["business_id", "order_id", "occurred_at"],
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["business_id", "order_id"],
            ["orders.business_id", "orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "operation", "idempotency_key"),
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processed', 'dead')",
            name=op.f("ck_outbox_messages_status_known"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_outbox_messages_attempts_nonnegative")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic", "order_id"),
    )
    op.create_index("ix_outbox_pending", "outbox_messages", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_pending", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_order_status_events_order", table_name="order_status_events")
    op.drop_table("order_status_events")
    op.drop_table("order_line_options")
    op.drop_table("order_lines")
    op.drop_index("ix_orders_business_promised", table_name="orders")
    op.drop_index("ix_orders_business_placed", table_name="orders")
    op.drop_table("orders")
    op.drop_constraint(
        op.f("ck_fulfillment_settings_max_orders_per_slot_bounds"),
        "fulfillment_settings",
        type_="check",
    )
    op.drop_column("fulfillment_settings", "max_orders_per_slot")
