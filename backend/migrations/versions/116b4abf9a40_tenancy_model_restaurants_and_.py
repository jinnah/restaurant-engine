"""Tenancy model: restaurants, memberships, and the deferred audit FK (M2B).

Creates the tenant root (``restaurants``, tenants domain) and the
tenant-owned ``memberships`` (identity domain, blueprint §7.1), then adds
the ``audit_events.restaurant_id`` foreign key that M2A deferred until a
``restaurants`` table existed.

The downgrade is audit-preserving (approved amendment 1): it nulls any
tenant-scoped ``audit_events.restaurant_id`` before dropping the FK and
tables, so audit history survives the downgrade with a null tenant id
rather than being deleted or orphaned. Downgrade is a development/scratch
operation only; production policy is forward-fix (blueprint §17.4).

Revision ID: 116b4abf9a40
Revises: 91774776ff27
Create Date: 2026-07-16 22:48:09.606528
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "116b4abf9a40"
down_revision: str | Sequence[str] | None = "91774776ff27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "restaurants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="provisioning", nullable=False),
        sa.Column("timezone", sa.Text(), server_default="America/New_York", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
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
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_restaurants_currency_iso4217_shape")
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$'",
            name=op.f("ck_restaurants_slug_canonical"),
        ),
        sa.CheckConstraint(
            "status IN ('provisioning', 'active', 'suspended', 'closed')",
            name=op.f("ck_restaurants_status_valid"),
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_restaurants_name_length")
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_restaurants_updated_after_creation")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_restaurants")),
        sa.UniqueConstraint("slug", name=op.f("uq_restaurants_slug")),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'manager', 'staff')", name=op.f("ck_memberships_role_valid")
        ),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            name=op.f("fk_memberships_restaurant_id_restaurants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint(
            "restaurant_id", "user_id", name=op.f("uq_memberships_restaurant_id_user_id")
        ),
    )
    op.create_index(
        "ix_memberships_restaurant_id_owner",
        "memberships",
        ["restaurant_id"],
        unique=False,
        postgresql_where=sa.text("role = 'owner'"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], unique=False)

    # The deferred M2A foreign key: audit_events.restaurant_id → restaurants.
    # The column and its composite cursor index were created in M2A; the FK
    # could not exist until restaurants did. RESTRICT keeps audit history
    # pinned to its tenant (audit never silently loses its subject).
    op.create_foreign_key(
        op.f("fk_audit_events_restaurant_id_restaurants"),
        "audit_events",
        "restaurants",
        ["restaurant_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Preserve audit history across the downgrade (approved amendment 1):
    # audit_events rows outlive the tenancy schema. Null out their
    # restaurant_id BEFORE dropping the FK/table so no row is deleted and no
    # dangling reference remains; the audit rows themselves stay intact.
    op.drop_constraint(
        op.f("fk_audit_events_restaurant_id_restaurants"),
        "audit_events",
        type_="foreignkey",
    )
    op.execute("UPDATE audit_events SET restaurant_id = NULL WHERE restaurant_id IS NOT NULL")

    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index(
        "ix_memberships_restaurant_id_owner",
        table_name="memberships",
        postgresql_where=sa.text("role = 'owner'"),
    )
    op.drop_table("memberships")
    op.drop_table("restaurants")
