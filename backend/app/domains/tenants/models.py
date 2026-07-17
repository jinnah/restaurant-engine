"""Tenant persistence model (M2B).

Tenants owns ``restaurants`` and the lifecycle state machine (blueprint
§7.2). Memberships live in the identity domain (§7.1) and reference this
table by name; tenants therefore imports no identity persistence.

Database-enforced invariants are named constraints here; the transition
*legality* (which previous state may become which) lives in
``tenants.lifecycle`` because a CHECK cannot see the prior value.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Restaurant(Base):
    """A tenant. Platform-scoped access; the root of every tenant-owned row."""

    __tablename__ = "restaurants"

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
            r"slug ~ '^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$'",
            name="slug_canonical",
        ),
        CheckConstraint(
            "status IN ('provisioning', 'active', 'suspended', 'closed')",
            name="status_valid",
        ),
        CheckConstraint(r"currency ~ '^[A-Z]{3}$'", name="currency_iso4217_shape"),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
    )
