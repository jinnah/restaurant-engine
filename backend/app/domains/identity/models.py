"""Identity persistence models (M2A, ADR-010; M2B memberships).

``users`` and ``sessions`` are **platform-global tables** (docs/04): they
deliberately carry no ``business_id``. Tenant scope attaches to a user
through ``memberships`` (Milestone 2B, blueprint §7.1: identity owns
memberships and roles), never to the account itself.

Database-enforced invariants live here as named constraints; state-machine
and policy rules live in the identity/businesses services.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """A person who can authenticate. Platform-global (docs/04)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # As entered (trimmed) for display; the normalized form is the identity.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Security kill-switch: checked at login and on every session validation.
    # No admin endpoint mutates it yet (approved decision #10).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Login backoff state (ADR-010): consecutive failures and the moment of
    # the last one. Always changed together; the pairing is DB-enforced.
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "email_normalized = lower(btrim(email_normalized))",
            name="email_normalized_canonical",
        ),
        CheckConstraint("email_normalized <> ''", name="email_normalized_not_empty"),
        CheckConstraint(
            "char_length(email) BETWEEN 3 AND 254",
            name="email_length",
        ),
        CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 120",
            name="display_name_length",
        ),
        CheckConstraint("password_hash <> ''", name="password_hash_not_empty"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_nonnegative"),
        CheckConstraint(
            "(failed_login_count = 0) = (last_failed_login_at IS NULL)",
            name="failed_login_state",
        ),
        CheckConstraint(
            "last_failed_login_at IS NULL OR last_failed_login_at >= created_at",
            name="last_failed_login_after_creation",
        ),
    )


class UserSession(Base):
    """Opaque database-backed browser session (ADR-010).

    Only the SHA-256 digest of the session token is stored. Validity is
    judged by the identity service: not revoked, inside the absolute bound,
    inside the idle window, and the owning user still active.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Synchronizer token (ADR-010): delivered via login / auth_session,
    # required in X-CSRF-Token on unsafe cookie-authenticated requests.
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("token_hash <> ''", name="token_hash_not_empty"),
        CheckConstraint("csrf_token <> ''", name="csrf_token_not_empty"),
        CheckConstraint("absolute_expires_at > created_at", name="absolute_expiry_after_creation"),
        CheckConstraint("last_used_at >= created_at", name="last_used_after_creation"),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="revocation_after_creation",
        ),
    )


class Membership(Base):
    """A user's role in one business (M2B; identity owns memberships).

    Tenant-owned: every row carries ``business_id`` (docs/04; ADR-012:
    Business is the tenant aggregate). The FK to ``businesses`` is declared
    by table name so identity never imports the businesses model — the
    acyclic dependency graph holds (identity → core only). Platform admins
    hold **no** membership rows; platform authority comes from
    ``users.is_platform_admin``.
    """

    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("role IN ('owner', 'manager', 'staff')", name="role_valid"),
        # One membership per user per business, tenant-leading (docs/04).
        # Unnamed so the metadata convention yields the deterministic
        # uq_memberships_business_id_user_id.
        UniqueConstraint("business_id", "user_id"),
        # Self-scoped "my memberships" path (user_id is not the leading column
        # of the unique constraint above).
        Index("ix_memberships_user_id", "user_id"),
        # Supports the owner-count guard for activation and the final-owner
        # invariant (approved M2B decision 6).
        Index(
            "ix_memberships_business_id_owner",
            "business_id",
            postgresql_where=text("role = 'owner'"),
        ),
    )
