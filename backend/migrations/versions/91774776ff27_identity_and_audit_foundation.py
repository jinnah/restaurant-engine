"""Identity and audit foundation (M2A, ADR-010).

Creates the three platform-global tables of the identity/session/audit
core: ``users`` (with login-backoff state), ``sessions`` (opaque
hashed-token browser sessions), and ``audit_events`` (append-only, BIGINT
identity cursor). ``audit_events.restaurant_id`` is created now as part of
the table's permanent shape; its foreign key arrives with the
``restaurants`` table in the M2B migration.

Revision ID: 91774776ff27
Revises: 96b88c334395
Create Date: 2026-07-16 19:29:20.218668
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "91774776ff27"
down_revision: str | Sequence[str] | None = "96b88c334395"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_normalized", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
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
            "email_normalized <> ''", name=op.f("ck_users_email_normalized_not_empty")
        ),
        sa.CheckConstraint("password_hash <> ''", name=op.f("ck_users_password_hash_not_empty")),
        sa.CheckConstraint(
            "(failed_login_count = 0) = (last_failed_login_at IS NULL)",
            name=op.f("ck_users_failed_login_state"),
        ),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 120", name=op.f("ck_users_display_name_length")
        ),
        sa.CheckConstraint(
            "char_length(email) BETWEEN 3 AND 254", name=op.f("ck_users_email_length")
        ),
        sa.CheckConstraint(
            "email_normalized = lower(btrim(email_normalized))",
            name=op.f("ck_users_email_normalized_canonical"),
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0", name=op.f("ck_users_failed_login_count_nonnegative")
        ),
        sa.CheckConstraint(
            "last_failed_login_at IS NULL OR last_failed_login_at >= created_at",
            name=op.f("ck_users_last_failed_login_after_creation"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email_normalized", name=op.f("uq_users_email_normalized")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("restaurant_id", sa.Uuid(), nullable=True),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("action <> ''", name=op.f("ck_audit_events_action_not_empty")),
        sa.CheckConstraint(
            "(target_type IS NULL) = (target_id IS NULL)",
            name=op.f("ck_audit_events_target_pairing"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_actor_user_id"), "audit_events", ["actor_user_id"], unique=False
    )
    op.create_index(
        "ix_audit_events_restaurant_id_id", "audit_events", ["restaurant_id", "id"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("csrf_token <> ''", name=op.f("ck_sessions_csrf_token_not_empty")),
        sa.CheckConstraint("token_hash <> ''", name=op.f("ck_sessions_token_hash_not_empty")),
        sa.CheckConstraint(
            "absolute_expires_at > created_at",
            name=op.f("ck_sessions_absolute_expiry_after_creation"),
        ),
        sa.CheckConstraint(
            "last_used_at >= created_at", name=op.f("ck_sessions_last_used_after_creation")
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name=op.f("ck_sessions_revocation_after_creation"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_audit_events_restaurant_id_id", table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_user_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
