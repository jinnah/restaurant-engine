"""Tenant persistence models (M2B/M2D, ADR-012/ADR-014).

Businesses owns the ``businesses`` table and the lifecycle state machine
(blueprint §7.2; ADR-012: Business is the tenant aggregate), plus the M2D
onboarding state (``business_invitations``) and product entitlements
(``feature_entitlements``). Memberships live in the identity domain (§7.1)
and reference ``businesses`` by name; conversely the M2D tables reference
``users`` by table name only, so businesses imports no identity
persistence in either direction.

Database-enforced invariants are named constraints here; the transition
*legality* (which previous state may become which) lives in
``businesses.lifecycle`` because a CHECK cannot see the prior value.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Business(Base):
    """A tenant. Platform-scoped access; the root of every tenant-owned row."""

    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Canonical slug: lowercased/trimmed and regex-validated in the create
    # schema; the DB CHECK is the final integrity boundary.
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="provisioning")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="America/New_York")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint(
            # 3-63 chars, lowercase alphanumeric with internal hyphens, no
            # leading/trailing hyphen. Matches the create-schema validator.
            r"slug ~ '^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$'",
            name="slug_canonical",
        ),
        CheckConstraint(
            "status IN ('provisioning', 'active', 'suspended', 'closed')",
            name="status_valid",
        ),
        CheckConstraint(r"currency ~ '^[A-Z]{3}$'", name="currency_iso4217_shape"),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
    )


class BusinessInvitation(Base):
    """A pending offer of membership in one business (M2D, ADR-014).

    Onboarding state owned by businesses (blueprint §7.2). The token is
    stored only as its SHA-256 hex digest; the raw value exists solely in
    the issuance response and the redeemer's request. ``users`` is
    referenced by table name so businesses imports no identity persistence.
    Token lifecycle timestamps are written on the database clock (ADR-014):
    ``expires_at`` is computed in SQL at insert and every validity check
    compares against ``now()`` in SQL, so application-clock skew can never
    change an expiry decision.
    """

    __tablename__ = "business_invitations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    # As entered (trimmed) for display; the normalized form is the identity,
    # matching the users contract.
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "email_normalized = lower(btrim(email_normalized))",
            name="email_normalized_canonical",
        ),
        CheckConstraint("email_normalized <> ''", name="email_normalized_not_empty"),
        CheckConstraint("role IN ('owner', 'manager', 'staff')", name="role_valid"),
        # Exactly a SHA-256 hex digest — never a raw token.
        CheckConstraint(r"token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_shape"),
        CheckConstraint("expires_at > created_at", name="expires_after_creation"),
        CheckConstraint(
            "accepted_at IS NULL OR accepted_at >= created_at",
            name="accepted_after_creation",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="revoked_after_creation",
        ),
        # A resolved invitation is accepted or revoked, never both.
        CheckConstraint(
            "NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="accepted_not_revoked",
        ),
        CheckConstraint(
            "(accepted_at IS NULL) = (accepted_user_id IS NULL)",
            name="accepted_pairing",
        ),
        # One live (unaccepted, unrevoked) invitation per business + email.
        # Backstop only: issuance serializes on the business row lock and
        # replaces the predecessor in the same transaction (ADR-014).
        Index(
            "uq_business_invitations_pending",
            "business_id",
            "email_normalized",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        # FK reverse lookups and the pending list.
        Index("ix_business_invitations_business_id", "business_id"),
    )


class FeatureEntitlement(Base):
    """One enabled product feature for one business (M2D, ADR-014).

    Presence means enabled; every feature is disabled by default. The value
    set lives in the append-only code registry (``businesses.features``) —
    deliberately not a DB CHECK, so adding a feature is not a migration
    (the audit-action pattern). Reads are fail-closed: a stored key missing
    from the registry is never surfaced as enabled.
    """

    __tablename__ = "feature_entitlements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("feature_key <> ''", name="feature_key_not_empty"),
        # Tenant-leading: also the lookup index for entitlement reads.
        UniqueConstraint("business_id", "feature_key"),
    )
