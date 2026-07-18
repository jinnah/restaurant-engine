"""Onboarding, recovery, and entitlements (M2D, ADR-014).

Three independent tables:

* ``business_invitations`` (businesses domain) — pending membership offers;
  token stored only as a SHA-256 digest; one live invitation per
  business + normalized email (partial unique backstop behind the
  business-row lock).
* ``password_reset_tokens`` (identity domain) — admin-issued single-use
  recovery credentials; one live token per user (approved M2A addendum).
* ``feature_entitlements`` (businesses domain) — presence-model product
  features; the value set lives in the append-only code registry, not a
  DB CHECK, so adding a feature is not a migration.

The downgrade drops the three tables (pre-launch operational state; audit
history lives in ``audit_events`` and is untouched). Downgrade order is
the reverse of creation.

Revision ID: 6fbce030db33
Revises: 116b4abf9a40
Create Date: 2026-07-18 01:14:37.511993
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6fbce030db33"
down_revision: str | Sequence[str] | None = "116b4abf9a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_normalized", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "email_normalized = lower(btrim(email_normalized))",
            name=op.f("ck_business_invitations_email_normalized_canonical"),
        ),
        sa.CheckConstraint(
            "email_normalized <> ''",
            name=op.f("ck_business_invitations_email_normalized_not_empty"),
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'manager', 'staff')",
            name=op.f("ck_business_invitations_role_valid"),
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_business_invitations_token_hash_shape"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_business_invitations_expires_after_creation"),
        ),
        sa.CheckConstraint(
            "accepted_at IS NULL OR accepted_at >= created_at",
            name=op.f("ck_business_invitations_accepted_after_creation"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name=op.f("ck_business_invitations_revoked_after_creation"),
        ),
        sa.CheckConstraint(
            "NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name=op.f("ck_business_invitations_accepted_not_revoked"),
        ),
        sa.CheckConstraint(
            "(accepted_at IS NULL) = (accepted_user_id IS NULL)",
            name=op.f("ck_business_invitations_accepted_pairing"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_business_invitations_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name=op.f("fk_business_invitations_invited_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_user_id"],
            ["users.id"],
            name=op.f("fk_business_invitations_accepted_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_invitations")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_business_invitations_token_hash")),
    )
    op.create_index(
        "uq_business_invitations_pending",
        "business_invitations",
        ["business_id", "email_normalized"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_index(
        "ix_business_invitations_business_id",
        "business_invitations",
        ["business_id"],
        unique=False,
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("issued_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_password_reset_tokens_token_hash_shape"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_password_reset_tokens_expires_after_creation"),
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR used_at >= created_at",
            name=op.f("ck_password_reset_tokens_used_after_creation"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name=op.f("ck_password_reset_tokens_revoked_after_creation"),
        ),
        sa.CheckConstraint(
            "NOT (used_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name=op.f("ck_password_reset_tokens_used_not_revoked"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["issued_by_user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_issued_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index(
        "uq_password_reset_tokens_live",
        "password_reset_tokens",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("used_at IS NULL AND revoked_at IS NULL"),
    )

    op.create_table(
        "feature_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("feature_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feature_key <> ''", name=op.f("ck_feature_entitlements_feature_key_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_feature_entitlements_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feature_entitlements")),
        sa.UniqueConstraint(
            "business_id",
            "feature_key",
            name=op.f("uq_feature_entitlements_business_id_feature_key"),
        ),
    )


def downgrade() -> None:
    # Reverse of creation. Operational state only — audit history lives in
    # audit_events and is untouched. Development/scratch operation only;
    # production policy is forward-fix (blueprint §17.4).
    op.drop_table("feature_entitlements")
    op.drop_index(
        "uq_password_reset_tokens_live",
        table_name="password_reset_tokens",
        postgresql_where=sa.text("used_at IS NULL AND revoked_at IS NULL"),
    )
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_business_invitations_business_id", table_name="business_invitations")
    op.drop_index(
        "uq_business_invitations_pending",
        table_name="business_invitations",
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.drop_table("business_invitations")
