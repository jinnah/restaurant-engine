"""Hours and fulfillment (M5A, ADR-025).

Three additive tenant-owned tables — ``business_hours``,
``schedule_exceptions``, ``fulfillment_settings`` — the blueprint §9
operations area. Nothing existing is altered: no ``businesses`` column, no
backfill, no rewrite of any earlier row. An absent ``fulfillment_settings``
row means the documented defaults (projected on read, materialized on
first write — the M4G-A mechanism), so existing tenants need no rows here
at all.

Invariants carried by the schema rather than by convention:

* minute encoding is D1: ``opens_minute`` 0-1439, ``closes_minute``
  1-2879 (above 1440 = the following local day), closes strictly after
  opens, one interval capped at 24 hours — weekly and exception rows
  carry the same CHECKs;
* an exception row stores a whole interval or none (the pairing CHECK);
  a NULL interval is "closed all day", and the partial unique index
  allows at most one such row per business and date;
* ``fulfillment_settings`` is a per-business singleton via the plain
  unique on ``business_id``, with every policy value CHECK-bounded.

Interval **non-overlap** is deliberately not a database constraint: the
service validates the submitted full set as a pure function under the
Business row lock; an EXCLUDE backstop would require the btree_gist
extension and is recorded in ADR-025 as a hardening candidate.

Value columns carry application-side values (server defaults on
timestamps alone), matching M3/M4A. The downgrade drops only these three
tables (dev/scratch only; production policy is forward-fix, §17.4).

Revision ID: c3d8f5a21e47
Revises: a41d9c7e5b30
Create Date: 2026-08-01 15:12:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d8f5a21e47"
down_revision: str | Sequence[str] | None = "a41d9c7e5b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("opens_minute", sa.Integer(), nullable=False),
        sa.Column("closes_minute", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "closes_minute > opens_minute",
            name=op.f("ck_business_hours_closes_after_opens"),
        ),
        sa.CheckConstraint(
            "closes_minute BETWEEN 1 AND 2879",
            name=op.f("ck_business_hours_closes_minute_bounds"),
        ),
        sa.CheckConstraint(
            "closes_minute - opens_minute <= 1440",
            name=op.f("ck_business_hours_interval_at_most_one_day"),
        ),
        sa.CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name=op.f("ck_business_hours_day_of_week_valid"),
        ),
        sa.CheckConstraint(
            "opens_minute BETWEEN 0 AND 1439",
            name=op.f("ck_business_hours_opens_minute_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_business_hours_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_hours")),
    )
    op.create_index(
        "ix_business_hours_business_id_day",
        "business_hours",
        ["business_id", "day_of_week"],
        unique=False,
    )

    op.create_table(
        "schedule_exceptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("exception_date", sa.Date(), nullable=False),
        sa.Column("opens_minute", sa.Integer(), nullable=True),
        sa.Column("closes_minute", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(opens_minute IS NULL) = (closes_minute IS NULL)",
            name=op.f("ck_schedule_exceptions_interval_pairing"),
        ),
        sa.CheckConstraint(
            "closes_minute IS NULL OR closes_minute > opens_minute",
            name=op.f("ck_schedule_exceptions_closes_after_opens"),
        ),
        sa.CheckConstraint(
            "closes_minute IS NULL OR closes_minute BETWEEN 1 AND 2879",
            name=op.f("ck_schedule_exceptions_closes_minute_bounds"),
        ),
        sa.CheckConstraint(
            "closes_minute IS NULL OR closes_minute - opens_minute <= 1440",
            name=op.f("ck_schedule_exceptions_interval_at_most_one_day"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) BETWEEN 1 AND 120",
            name=op.f("ck_schedule_exceptions_note_length"),
        ),
        sa.CheckConstraint(
            "opens_minute IS NULL OR opens_minute BETWEEN 0 AND 1439",
            name=op.f("ck_schedule_exceptions_opens_minute_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_schedule_exceptions_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule_exceptions")),
    )
    op.create_index(
        "ix_schedule_exceptions_business_id_date",
        "schedule_exceptions",
        ["business_id", "exception_date"],
        unique=False,
    )
    op.create_index(
        "uq_schedule_exceptions_one_closed_per_date",
        "schedule_exceptions",
        ["business_id", "exception_date"],
        unique=True,
        postgresql_where=sa.text("opens_minute IS NULL"),
    )

    op.create_table(
        "fulfillment_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("pickup_enabled", sa.Boolean(), nullable=False),
        sa.Column("asap_enabled", sa.Boolean(), nullable=False),
        sa.Column("lead_time_minutes", sa.Integer(), nullable=False),
        sa.Column("slot_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("last_order_before_close_minutes", sa.Integer(), nullable=False),
        sa.Column("max_days_ahead", sa.Integer(), nullable=False),
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
            "last_order_before_close_minutes BETWEEN 0 AND 240",
            name=op.f("ck_fulfillment_settings_last_order_bounds"),
        ),
        sa.CheckConstraint(
            "lead_time_minutes BETWEEN 0 AND 1440",
            name=op.f("ck_fulfillment_settings_lead_time_bounds"),
        ),
        sa.CheckConstraint(
            "max_days_ahead BETWEEN 0 AND 30",
            name=op.f("ck_fulfillment_settings_max_days_ahead_bounds"),
        ),
        sa.CheckConstraint(
            "slot_interval_minutes BETWEEN 5 AND 120",
            name=op.f("ck_fulfillment_settings_slot_interval_bounds"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_fulfillment_settings_updated_after_creation"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_fulfillment_settings_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fulfillment_settings")),
        sa.UniqueConstraint("business_id", name=op.f("uq_fulfillment_settings_business_id")),
    )


def downgrade() -> None:
    # Drops only what this revision added; every earlier table and row is
    # untouched. Dev/scratch only — production policy is forward-fix.
    op.drop_table("fulfillment_settings")
    op.drop_index(
        "uq_schedule_exceptions_one_closed_per_date",
        table_name="schedule_exceptions",
        postgresql_where=sa.text("opens_minute IS NULL"),
    )
    op.drop_index("ix_schedule_exceptions_business_id_date", table_name="schedule_exceptions")
    op.drop_table("schedule_exceptions")
    op.drop_index("ix_business_hours_business_id_day", table_name="business_hours")
    op.drop_table("business_hours")
