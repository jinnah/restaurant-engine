"""Media persistence models (M3C, ADR-017).

One general asset model plus relational variant rows (approved M3C
architecture). Every table is tenant-owned and carries ``business_id``
(docs/04); ``media_assets`` exposes ``UNIQUE (business_id, id)`` so
attachments (``menu_items.image_media_id`` in M3C) are composite
tenant-safe foreign keys — a cross-tenant attachment is a database
error. ``businesses`` is referenced by table name only (the Membership
string-FK pattern), so media imports no businesses persistence.

Asset identity is immutable: replacement is a new asset, never an
in-place rewrite. The stored bytes are the re-encoded canonical WebP
and its variants — the original upload is not retained — so every
``checksum_sha256`` is the checksum of bytes actually in storage.
``kind`` is CHECK-limited to ``image`` today; extending to video later
is an additive migration (approved decision 5). Byte sizes are BIGINT
(the audit-id precedent; immune to pathological growth).

Lifecycle (database clock, ADR-017 R7): uploads start ``pending`` with
``pending_expires_at = now() + 48 hours`` computed in SQL at insert;
first valid attachment promotes to ``active`` and clears the expiry
(the pairing CHECK makes the two facts inseparable). At exact expiry
the asset is already expired (``pending_expires_at <= now()``).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class MediaAsset(Base):
    """One processed, stored media asset of one business (tenant-owned)."""

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    # CHECK-limited to 'image' in M3C; video is a later additive migration.
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="image")
    # 'pending' (unattached, TTL on the DB clock) or 'active' (ever
    # attached; promotion is one-way and never reversed).
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # Set in SQL at insert (now() + 48 h) for pending rows; NULL for
    # active rows — the pairing CHECK enforces the equivalence.
    pending_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Sanitized display metadata only (<= 160); never used in storage keys.
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    # Recorded as received, never trusted (magic bytes + decoded format
    # are authoritative).
    declared_content_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Authoritative detected source format (static allowlist).
    source_format: Mapped[str] = mapped_column(Text, nullable=False)
    # Canonical (post-processing) facts: WebP <= 2560 px longest side.
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # SHA-256 (lowercase hex) of the canonical stored object.
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("kind IN ('image')", name="kind_known"),
        CheckConstraint("status IN ('pending', 'active')", name="status_known"),
        CheckConstraint(
            "(status = 'pending') = (pending_expires_at IS NOT NULL)",
            name="pending_expiry_pairing",
        ),
        CheckConstraint(
            "char_length(original_filename) BETWEEN 1 AND 160",
            name="original_filename_length",
        ),
        CheckConstraint(
            "char_length(declared_content_type) BETWEEN 1 AND 160",
            name="declared_content_type_length",
        ),
        CheckConstraint("source_format IN ('jpeg', 'png', 'webp')", name="source_format_known"),
        CheckConstraint("width BETWEEN 1 AND 2560", name="width_range"),
        CheckConstraint("height BETWEEN 1 AND 2560", name="height_range"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint("checksum_sha256 ~ '^[0-9a-f]{64}$'", name="checksum_sha256_format"),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
        # Composite-FK target: attachments reference (business_id, id) so a
        # cross-tenant attachment is a database error (docs/04).
        UniqueConstraint("business_id", "id"),
        # Tenant-scoped list path (newest first).
        Index("ix_media_assets_business_id_created_at", "business_id", "created_at"),
        # Sweep/TTL path: expired-pending candidates only.
        Index(
            "ix_media_assets_pending_expiry",
            "business_id",
            "pending_expires_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )


class MediaAssetVariant(Base):
    """One generated responsive rendition of one asset (M3C, ruling R4).

    Variants exist only when strictly smaller than the canonical width —
    never upscaled — and die with their asset (CASCADE). Each row records
    the size and checksum of the bytes actually retained in storage, so
    the database is the authoritative media inventory for backup
    verification and the sweep.
    """

    __tablename__ = "media_asset_variants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Logical variant name; the closed set mirrors policies.VARIANT_WIDTHS.
    variant: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("variant IN ('w320', 'w640', 'w1280')", name="variant_known"),
        CheckConstraint("width BETWEEN 1 AND 2560", name="width_range"),
        CheckConstraint("height BETWEEN 1 AND 2560", name="height_range"),
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint("checksum_sha256 ~ '^[0-9a-f]{64}$'", name="checksum_sha256_format"),
        # Tenant-safe parent relationship; variants die with their asset.
        ForeignKeyConstraint(
            ["business_id", "asset_id"],
            ["media_assets.business_id", "media_assets.id"],
            ondelete="CASCADE",
        ),
        # One row per logical variant; also the read path for an asset's
        # variant set and the non-multiplying byte aggregate (business_id
        # leads, docs/04).
        UniqueConstraint("business_id", "asset_id", "variant"),
    )
