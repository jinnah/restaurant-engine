"""Storefront persistence models (M4A, ADR-020).

One tenant-owned table, ``storefront_versions``, holding every draft,
published, and archived composition of every business (blueprint §7.4).
``businesses`` and ``users`` are referenced by table name only, so
storefront imports no other domain's persistence.

The version lifecycle::

    draft ──publish──▶ published ──(next publish)──▶ archived
      ▲                    │
      └──── seeds new ─────┘

Two database-enforced singletons carry the blueprint §9.2 invariant "one
active draft and at most one active published storefront version per
restaurant": partial unique indexes on ``state``. Version numbers are
minted **at publication**, so a draft carries ``version_number IS NULL``
and the paired CHECK makes the two facts inseparable — a draft with a
number, or a published row without one, is unstorable.

``design_variant`` lives here rather than on ``businesses`` (ADR-020 D4):
published and archived rows keep the variant they were rendered with, so
reassigning a design never rewrites how history looked. ``lock_version``
is the optimistic-concurrency token for the mutable draft, closing the
ADR-017 D5 deferral for composition; catalog keeps its row-lock semantics.

M4A ships the table and its invariants only. The services that move rows
between states — publish, restore, platform design assignment — are M4B.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VersionState(StrEnum):
    """Lifecycle state of one storefront version.

    ``draft`` is the single mutable working copy; ``published`` is the one
    version the public projection may serve; ``archived`` is immutable
    history. Transition legality lives in the M4B service — a CHECK cannot
    see the previous value (the ``businesses.lifecycle`` precedent).
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class StorefrontVersion(Base):
    """One composition version of one business (tenant-owned)."""

    __tablename__ = "storefront_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL while draft; minted from max(version_number) + 1 at publication.
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The registry contract this config validates against, stored so a
    # later registry change can migrate or reject deliberately.
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Platform-governed (blueprint §12.3); validated against the code-owned
    # registry, never a tenant-submitted value.
    design_variant: Mapped[str] = mapped_column(Text, nullable=False)
    # The sanctioned JSONB use (blueprint §9.1): versioned storefront
    # composition. Validated by the section registry before it is stored.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Optimistic concurrency for the mutable draft: every effective draft
    # mutation increments it, so a stale editor's write is a 409 rather
    # than a silent overwrite.
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Provenance: the published version a draft was seeded from, or the
    # archived version a restore copied. Tenant-safe composite FK below.
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Owner-facing history reads "who published" from here, so no separate
    # publication-events table exists (ADR-020 D7).
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('draft', 'published', 'archived')",
            name="state_valid",
        ),
        CheckConstraint(
            "version_number IS NULL OR version_number > 0",
            name="version_number_positive",
        ),
        # A draft has no number and a numbered row is not a draft — one
        # constraint, both directions, so neither fact can drift.
        CheckConstraint(
            "(state = 'draft') = (version_number IS NULL)",
            name="draft_has_no_version_number",
        ),
        CheckConstraint("lock_version >= 0", name="lock_version_nonnegative"),
        CheckConstraint("schema_version > 0", name="schema_version_positive"),
        CheckConstraint(
            "source_version_id IS NULL OR source_version_id <> id",
            name="source_not_self",
        ),
        CheckConstraint("design_variant <> ''", name="design_variant_not_empty"),
        # Publication facts arrive together or not at all.
        CheckConstraint(
            "(published_at IS NULL) = (published_by_user_id IS NULL)",
            name="publication_pairing",
        ),
        # Draft rows carry no publication fields; published and archived
        # rows always carry theirs.
        CheckConstraint(
            "(state = 'draft') = (published_at IS NULL)",
            name="draft_not_published",
        ),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
        # The config column is an object, never a bare array, string, or
        # null wrapped in JSONB. Pydantic already guarantees this on every
        # application path; the CHECK is the integrity boundary for any
        # path that is not the application (blueprint §3.4).
        CheckConstraint("jsonb_typeof(config) = 'object'", name="config_is_object"),
        # Composite-FK target for the tenant-safe self reference below.
        UniqueConstraint("business_id", "id"),
        # Provenance can never cross tenants: the (business_id, id) pair
        # must exist in this same table, so a version can only ever be
        # seeded or restored from one of its own business's versions.
        # Named explicitly: the convention would generate
        # ``fk_storefront_versions_business_id_source_version_id_storefront_versions``
        # (70 characters), and PostgreSQL silently truncates identifiers at
        # 63 bytes — the model and the database would then disagree about a
        # constraint's name. A permanent test bounds every generated name.
        ForeignKeyConstraint(
            ["business_id", "source_version_id"],
            ["storefront_versions.business_id", "storefront_versions.id"],
            name="fk_storefront_versions_source_version",
            ondelete="RESTRICT",
        ),
        # The two §9.2 singletons.
        Index(
            "uq_storefront_versions_one_draft",
            "business_id",
            unique=True,
            postgresql_where=text("state = 'draft'"),
        ),
        Index(
            "uq_storefront_versions_one_published",
            "business_id",
            unique=True,
            postgresql_where=text("state = 'published'"),
        ),
        # Version numbers are unique per business among the rows that have
        # one; drafts (NULL) are excluded rather than relying on NULL
        # distinctness, so the intent is readable in the schema.
        #
        # This is also the owner-facing history index, and no separate
        # descending index exists — measured, not assumed: with an ordered
        # path available PostgreSQL answers
        # ``WHERE business_id = ? AND version_number IS NOT NULL
        #   ORDER BY version_number DESC``
        # with ``Index Scan Backward`` on this index and **no Sort node**.
        #
        # The M4B history query must therefore carry the predicate
        # ``version_number IS NOT NULL`` literally. A partial index is only
        # considered when the query implies its predicate, and PostgreSQL's
        # prover does not consult CHECK constraints: the equivalent-looking
        # ``state <> 'draft'`` does **not** qualify, even though
        # ``draft_has_no_version_number`` makes the two conditions identical
        # in practice (measured: that form falls back to a sequential scan).
        Index(
            "uq_storefront_versions_business_id_version_number",
            "business_id",
            "version_number",
            unique=True,
            postgresql_where=text("version_number IS NOT NULL"),
        ),
        # Draft/published lookup by business.
        Index("ix_storefront_versions_business_id_state", "business_id", "state"),
    )
