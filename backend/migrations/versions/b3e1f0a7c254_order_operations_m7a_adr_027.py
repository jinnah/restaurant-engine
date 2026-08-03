"""Order operations columns (M7A, ADR-027).

Two additive concerns, one revision:

- ``orders.estimated_ready_at`` (nullable timestamptz) — the kitchen's
  live prep estimate (ruling D7). ``promised_pickup_at`` stays immutable
  as placed: the promise the customer chose; the estimate is the
  kitchen's updatable answer, shown on the tracker when present.
- ``fulfillment_settings.ordering_paused`` / ``pause_note`` /
  ``pause_resume_at`` (ruling D8) — the temporary, customer-visible
  ordering pause. Effectiveness is computed, never scheduled:
  ``paused AND (resume_at IS NULL OR now < resume_at)``. The note is a
  bounded plain-text customer-facing explanation. Server defaults keep
  every existing row unpaused.

No new index: the operational list reads newest-first by the dense,
tenant-scoped ``order_number`` behind an exclusive cursor (ruling D6 as
amended in delivery — the existing ``(business_id, order_number)``
unique already serves it; order ids are random UUID4, so an id cursor
would not be a time cursor).

What stays service-enforced: the transition machine and its locks, the
estimate's legal states, and pause enforcement at placement. Additive
only; no backfill. ``downgrade`` exists for development and scratch
databases — production policy is forward-fix (blueprint §17.4).

Revision ID: b3e1f0a7c254
Revises: e7a2c94d51b8
Create Date: 2026-08-02
"""

import sqlalchemy as sa
from alembic import op

revision = "b3e1f0a7c254"
down_revision = "e7a2c94d51b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("estimated_ready_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fulfillment_settings",
        sa.Column(
            "ordering_paused",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "fulfillment_settings",
        sa.Column("pause_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "fulfillment_settings",
        sa.Column("pause_resume_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fulfillment_settings", "pause_resume_at")
    op.drop_column("fulfillment_settings", "pause_note")
    op.drop_column("fulfillment_settings", "ordering_paused")
    op.drop_column("orders", "estimated_ready_at")
