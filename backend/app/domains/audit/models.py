"""Audit persistence model (M2A).

``audit_events`` is a **platform-global table with optional tenant scope**
(docs/04): platform-level events carry a NULL ``business_id``. The table
is append-only by application discipline — the audit service exposes only
``record``; revoking UPDATE/DELETE at the database-role level is a
Milestone 8 production-hardening item.

The BIGINT identity primary key is deliberate: it gives the append-only
stream a monotonic order for cursor pagination (M2D). It is exposed only
through the platform-capability-gated audit API, never publicly.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEvent(Base):
    """One append-only security or business event (blueprint §7.8)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Value set lives in the append-only code registry (audit.actions);
    # deliberately not a DB CHECK so adding an action is not a migration.
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL actor = anonymous or system (e.g. failed login for an unknown
    # email). SET NULL: audit history outlives any future account deletion.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Tenant scope (M2B): NULL = platform-level event. The FK to the tenant
    # root is declared by table name so audit imports no businesses code
    # (same string-FK pattern as identity's Membership). RESTRICT keeps
    # audit history pinned to its tenant.
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=True
    )
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Safe structured summary built only from per-action typed schemas
    # (audit.details) — never free-form dicts, never secrets.
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("action <> ''", name="action_not_empty"),
        CheckConstraint(
            "(target_type IS NULL) = (target_id IS NULL)",
            name="target_pairing",
        ),
        # Serves the tenant-filtered cursor page (WHERE business_id = ?
        # AND id < ? ORDER BY id DESC) directly (approved addendum item 8).
        Index("ix_audit_events_business_id_id", "business_id", "id"),
    )
