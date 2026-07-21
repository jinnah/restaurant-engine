"""Catalog persistence models (M3A, ADR-017).

Catalog owns menu categories, menu items, and their dietary tags
(blueprint §7.3). Every table is tenant-owned and carries ``business_id``
(docs/04); parents expose ``UNIQUE (business_id, id)`` so children join
through **composite tenant-safe foreign keys** — a child row can never
reference another tenant's parent, even if application checks were
bypassed. ``businesses`` is referenced by table name only, so catalog
imports no businesses persistence (the Membership string-FK pattern).

Database-enforced invariants are named constraints here; count limits,
the featured policy, and position normalization live in
``catalog.policies``/``catalog.service`` because a CHECK cannot count
rows. Position uniqueness is DEFERRABLE INITIALLY DEFERRED so a full-set
reorder can rewrite a permutation in one transaction; the constraint
still checks at commit.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class MenuCategory(Base):
    """One menu section of one business (tenant-owned)."""

    __tablename__ = "menu_categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    # Normalized on write (R6): trimmed, internal whitespace collapsed, NFC.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Dense 0..n-1 within the business; rewritten transactionally on
    # create/delete/reorder (docs/03: reorder normalizes positions).
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint(
            "description IS NULL OR char_length(description) <= 500",
            name="description_length",
        ),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
        # Composite-FK target: children reference (business_id, id) so a
        # cross-tenant parent is a database error (docs/04).
        UniqueConstraint("business_id", "id"),
        # Dense positions are DB-enforced; DEFERRED so a reorder may pass
        # through a transient permutation inside one transaction.
        UniqueConstraint("business_id", "position", deferrable=True, initially="DEFERRED"),
        # Case-insensitive category-name uniqueness per business (R6). An
        # expression index is the race-safe invariant; the service precheck
        # only improves the error message.
        Index(
            "uq_menu_categories_name_ci",
            "business_id",
            text("lower(name)"),
            unique=True,
        ),
    )


class MenuItem(Base):
    """One sellable menu item (tenant-owned; grandparent: businesses)."""

    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Integer minor units (blueprint §3.5); the currency is the business's
    # own ``businesses.currency`` — deliberately no per-item currency column
    # (docs/03: currency comes from the tenant).
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    # Dense 0..n-1 within (business_id, category_id).
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # "Sold out today" and "hidden" are separate states (docs/03):
    # is_available is the transient sellability toggle (staff-reachable);
    # is_hidden removes the item from public view entirely.
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Counted against the centralized featured policy (R1: max 6 per
    # business, hidden items included; hiding never clears the flag).
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # M3C item image attachment: at most one image per item, referenced
    # by media identifier through the composite tenant-safe FK below
    # (RESTRICT backs "referenced media cannot be deleted"). Alt text is
    # contextual — it belongs to this attachment, not the asset (R2
    # "contextual image alt") — and requires an image (pairing CHECK).
    image_media_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    image_alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint(
            "description IS NULL OR char_length(description) <= 1000",
            name="description_length",
        ),
        CheckConstraint("price_minor >= 0", name="price_nonnegative"),
        # Approved price ceiling (ADR-017 F1 ruling): the schema rejects
        # above-bound values with a 422; this CHECK is the final integrity
        # boundary so direct inserts cannot bypass the approved range.
        CheckConstraint("price_minor <= 10000000", name="price_maximum"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
        # Tenant-safe parent relationship: the pair must exist in
        # menu_categories, so an item can never sit under another tenant's
        # category (docs/04 composite-FK contract). RESTRICT backs the
        # empty-only category deletion rule (D7).
        ForeignKeyConstraint(
            ["business_id", "category_id"],
            ["menu_categories.business_id", "menu_categories.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "image_alt_text IS NULL OR image_media_id IS NOT NULL",
            name="image_alt_requires_image",
        ),
        CheckConstraint(
            "image_alt_text IS NULL OR char_length(image_alt_text) <= 300",
            name="image_alt_text_length",
        ),
        # Tenant-safe attachment (M3C): the pair must exist in
        # media_assets, so an item can never show another tenant's image;
        # RESTRICT makes deleting a referenced asset a database error.
        ForeignKeyConstraint(
            ["business_id", "image_media_id"],
            ["media_assets.business_id", "media_assets.id"],
            ondelete="RESTRICT",
        ),
        # Composite-FK target for menu_item_dietary_tags.
        UniqueConstraint("business_id", "id"),
        UniqueConstraint(
            "business_id",
            "category_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Case-insensitive item-name uniqueness within a category (R6); the
        # same normalized name may exist in different categories.
        Index(
            "uq_menu_items_name_ci",
            "business_id",
            "category_id",
            text("lower(name)"),
            unique=True,
        ),
        # Serves the featured-count guard under the business lock (R1) —
        # the Membership partial-owner-index pattern.
        Index(
            "ix_menu_items_business_id_featured",
            "business_id",
            postgresql_where=text("is_featured"),
        ),
    )


class MenuItemDietaryTag(Base):
    """One dietary attribute of one menu item (M3A, ruling D6).

    The value set lives in the append-only code registry
    (``catalog.dietary``) — deliberately not a DB CHECK, so adding a tag is
    not a migration (the feature-key/audit-action pattern). Reads are
    fail-closed: a stored tag missing from the registry is never surfaced.
    The lowercase-canonical CHECK is the storage invariant.
    """

    __tablename__ = "menu_item_dietary_tags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tag: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tag = lower(btrim(tag))", name="tag_canonical"),
        CheckConstraint("tag <> ''", name="tag_not_empty"),
        # Pure child attribute rows die with their item — no history value
        # (contrast the RESTRICT FKs elsewhere); tenant-safe pair reference.
        ForeignKeyConstraint(
            ["business_id", "item_id"],
            ["menu_items.business_id", "menu_items.id"],
            ondelete="CASCADE",
        ),
        # Tenant-leading; also the read path for an item's tag set.
        UniqueConstraint("business_id", "item_id", "tag"),
    )


class ModifierGroup(Base):
    """One customization group of one menu item (M3B, ADR-017 ruling D10).

    Belongs to exactly one item; no reusable cross-item library. The
    selection rules' **numeric domain** is database-enforced in three
    separately named CHECKs (min 0-30; max NULL or 1-30; min ≤ max — the
    30 mirrors ``policies.MAX_MODIFIER_OPTIONS_PER_GROUP``). Whether the
    rules are *currently satisfiable* by the group's available options is
    computed at read time and never stored (report-only, ADR-017).
    ``max_select`` NULL means unlimited by configuration, still bounded by
    active options at use time (docs/03).
    """

    __tablename__ = "modifier_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Application-side defaults only (ADR-017): a direct SQL insert that
    # omits a value column fails explicitly instead of silently acquiring
    # a different default than API-created rows.
    min_select: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_select: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("min_select >= 0 AND min_select <= 30", name="min_select_range"),
        CheckConstraint(
            "max_select IS NULL OR (max_select >= 1 AND max_select <= 30)",
            name="max_select_range",
        ),
        CheckConstraint("max_select IS NULL OR min_select <= max_select", name="min_le_max"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
        # Tenant-safe parent relationship; a group dies with its item
        # (approved cascade direction).
        ForeignKeyConstraint(
            ["business_id", "item_id"],
            ["menu_items.business_id", "menu_items.id"],
            ondelete="CASCADE",
        ),
        # Composite-FK target for modifier_options.
        UniqueConstraint("business_id", "id"),
        UniqueConstraint(
            "business_id",
            "item_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Case-insensitive group-name uniqueness within an item (R6).
        Index(
            "uq_modifier_groups_name_ci",
            "business_id",
            "item_id",
            text("lower(name)"),
            unique=True,
        ),
    )


class ModifierOption(Base):
    """One selectable option of one modifier group (M3B).

    Tenant-owned grandchild (docs/04 names modifier options verbatim).
    ``price_delta_minor`` shares the catalog price bound (F1/D1:
    0..MAX_PRICE_MINOR, DB-enforced); ``is_available`` is the transient
    operator toggle, distinct from deletion — it feeds the parent group's
    computed ``active_option_count``. Deliberately no
    ``UNIQUE (business_id, id)``: nothing references options (M6 order
    lines snapshot, never FK — blueprint §7.3/§7.7).
    """

    __tablename__ = "modifier_options"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_delta_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("price_delta_minor >= 0", name="price_delta_nonnegative"),
        CheckConstraint("price_delta_minor <= 10000000", name="price_delta_maximum"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
        # Tenant-safe parent relationship; options die with their group.
        ForeignKeyConstraint(
            ["business_id", "group_id"],
            ["modifier_groups.business_id", "modifier_groups.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "business_id",
            "group_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Case-insensitive option-name uniqueness within a group (R6).
        Index(
            "uq_modifier_options_name_ci",
            "business_id",
            "group_id",
            text("lower(name)"),
            unique=True,
        ),
    )
