"""Catalog API schemas (M3A, ADR-017).

Commands are strict (``extra="forbid"``) and normalize their inputs:
names through ``policies.normalize_name`` (R6), descriptions trimmed with
empty treated as absent, dietary tags canonicalized to lowercase and
validated against the registry (D6). Responses are explicit projections —
never serialized ORM objects.

PATCH semantics: a field changes only when it is present in the request
body (``model_fields_set``). ``description`` is the only nullable field —
an explicit ``null`` clears it; an explicit ``null`` for any other field
is rejected.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.catalog import dietary, policies


def _normalized_name(value: str) -> str:
    name = policies.normalize_name(value)
    if not name:
        msg = "name must not be blank"
        raise ValueError(msg)
    if len(name) > policies.MAX_NAME_LENGTH:
        msg = f"name must be at most {policies.MAX_NAME_LENGTH} characters"
        raise ValueError(msg)
    return name


def _normalized_description(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > max_length:
        msg = f"description must be at most {max_length} characters"
        raise ValueError(msg)
    return trimmed


def _normalized_tags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for raw in values:
        tag = raw.strip().lower()
        if not dietary.is_known_tag(tag):
            msg = f"unknown dietary tag: {raw!r}"
            raise ValueError(msg)
        if tag in tags:
            msg = f"duplicate dietary tag: {tag!r}"
            raise ValueError(msg)
        tags.append(tag)
    if len(tags) > policies.MAX_DIETARY_TAGS_PER_ITEM:
        msg = f"at most {policies.MAX_DIETARY_TAGS_PER_ITEM} dietary tags per item"
        raise ValueError(msg)
    return tags


def _unique_ids(values: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(values)) != len(values):
        msg = "ids must not contain duplicates"
        raise ValueError(msg)
    return values


# --- Categories --------------------------------------------------------------


class CategoryCreate(BaseModel):
    """Create a menu category (appended at the end of the menu)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _normalized_name(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return _normalized_description(value, max_length=policies.MAX_CATEGORY_DESCRIPTION_LENGTH)


class CategoryUpdate(BaseModel):
    """Partial category update; only supplied fields change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    is_visible: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _normalized_name(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return _normalized_description(value, max_length=policies.MAX_CATEGORY_DESCRIPTION_LENGTH)

    @model_validator(mode="after")
    def _no_null_for_non_nullable(self) -> "CategoryUpdate":
        # description is the only clearable field; an explicit null for the
        # others is a contradiction, not a no-op.
        for field in ("name", "is_visible"):
            if field in self.model_fields_set and getattr(self, field) is None:
                msg = f"{field} cannot be null"
                raise ValueError(msg)
        return self


class CategoryReorder(BaseModel):
    """Full-set category reorder: every category id, in the new order."""

    model_config = ConfigDict(extra="forbid")

    ordered_category_ids: list[uuid.UUID] = Field(
        min_length=1, max_length=policies.MAX_CATEGORIES_PER_BUSINESS
    )

    @field_validator("ordered_category_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return _unique_ids(value)


class CategorySummary(BaseModel):
    """One category (administrative projection)."""

    id: uuid.UUID
    name: str
    description: str | None
    position: int
    is_visible: bool
    created_at: datetime
    updated_at: datetime


# --- Items -------------------------------------------------------------------


class ItemCreate(BaseModel):
    """Create a menu item (appended at the end of its category).

    New items start available, not hidden, and not featured; those states
    change through PATCH and the availability command.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    price_minor: int = Field(ge=0, le=policies.MAX_PRICE_MINOR)
    dietary_tags: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _normalized_name(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return _normalized_description(value, max_length=policies.MAX_ITEM_DESCRIPTION_LENGTH)

    @field_validator("dietary_tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return _normalized_tags(value)


class ItemUpdate(BaseModel):
    """Partial item update; only supplied fields change.

    ``category_id`` moves the item (appended at the end of the destination
    category). ``is_available`` is deliberately absent: availability is the
    separate staff-reachable command (ruling D4), never part of this PATCH.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    price_minor: int | None = Field(default=None, ge=0, le=policies.MAX_PRICE_MINOR)
    category_id: uuid.UUID | None = None
    is_hidden: bool | None = None
    is_featured: bool | None = None
    dietary_tags: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _normalized_name(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return _normalized_description(value, max_length=policies.MAX_ITEM_DESCRIPTION_LENGTH)

    @field_validator("dietary_tags")
    @classmethod
    def _tags(cls, value: list[str] | None) -> list[str] | None:
        return _normalized_tags(value) if value is not None else None

    @model_validator(mode="after")
    def _no_null_for_non_nullable(self) -> "ItemUpdate":
        non_nullable = (
            "name",
            "price_minor",
            "category_id",
            "is_hidden",
            "is_featured",
            "dietary_tags",
        )
        for field in non_nullable:
            if field in self.model_fields_set and getattr(self, field) is None:
                msg = f"{field} cannot be null"
                raise ValueError(msg)
        return self


class ItemReorder(BaseModel):
    """Full-set item reorder within one category."""

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    ordered_item_ids: list[uuid.UUID] = Field(
        min_length=1, max_length=policies.MAX_ITEMS_PER_CATEGORY
    )

    @field_validator("ordered_item_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return _unique_ids(value)


class ItemAvailabilitySet(BaseModel):
    """The availability command body ("sold out today" toggle)."""

    model_config = ConfigDict(extra="forbid")

    is_available: bool


class ItemImageSet(BaseModel):
    """The item-image command body (M3C): attach/replace/clear + alt text.

    Both fields are genuinely nullable: ``media_id`` null clears the image;
    ``alt_text`` null removes the description. Alt text without an image is
    rejected (the database also enforces this). Empty/whitespace alt text
    normalizes to null.
    """

    model_config = ConfigDict(extra="forbid")

    media_id: uuid.UUID | None = None
    alt_text: str | None = None

    @field_validator("alt_text")
    @classmethod
    def _alt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > policies.MAX_IMAGE_ALT_LENGTH:
            msg = f"alt_text must be at most {policies.MAX_IMAGE_ALT_LENGTH} characters"
            raise ValueError(msg)
        return trimmed

    @model_validator(mode="after")
    def _alt_requires_image(self) -> "ItemImageSet":
        if self.alt_text is not None and self.media_id is None:
            msg = "alt_text requires an image"
            raise ValueError(msg)
        return self


class ItemSummary(BaseModel):
    """One menu item (administrative projection).

    ``price_minor`` is integer minor units; the currency is the business's
    own (``businesses.currency``) and is deliberately not repeated here.
    """

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    price_minor: int
    position: int
    is_available: bool
    is_hidden: bool
    is_featured: bool
    dietary_tags: list[str]
    # M3C attachment: at most one image and its contextual alt text (null
    # when no image is attached).
    image_media_id: uuid.UUID | None
    image_alt_text: str | None
    created_at: datetime
    updated_at: datetime


# --- Aggregate administrative menu -------------------------------------------


class CategoryWithItems(CategorySummary):
    """A category and its items in position order (hidden included)."""

    items: list[ItemSummary]


class AdminMenu(BaseModel):
    """The complete administrative menu tree.

    Includes hidden categories/items (this is the management view); M3A
    carries no modifier or media data (they arrive with M3B/M3C).
    """

    categories: list[CategoryWithItems]


class DeletedResponse(BaseModel):
    """Explicit confirmation body for delete commands (the M2D
    ``InvitationRevokedResponse`` pattern — commands return a clear result,
    blueprint §10.4)."""

    status: Literal["deleted"] = "deleted"


# --- Modifiers (M3B, ADR-017) -------------------------------------------------


class ModifierGroupCreate(BaseModel):
    """Create a modifier group (appended at the end of the item's groups).

    A group may be created with zero options: satisfiability is computed
    and report-only (D5). ``max_select`` null means unlimited.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    min_select: int = Field(default=0, ge=0, le=policies.MAX_MODIFIER_OPTIONS_PER_GROUP)
    max_select: int | None = Field(default=None, ge=1, le=policies.MAX_MODIFIER_OPTIONS_PER_GROUP)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _normalized_name(value)

    @model_validator(mode="after")
    def _min_le_max(self) -> "ModifierGroupCreate":
        if self.max_select is not None and self.min_select > self.max_select:
            msg = "min_select cannot exceed max_select"
            raise ValueError(msg)
        return self


class ModifierGroupUpdate(BaseModel):
    """Partial group update; only supplied fields change.

    ``max_select`` is the one genuinely nullable field: an explicit null
    sets the group to unlimited (the description-clearing pattern). When
    only one side of the min/max pair is supplied, the service validates
    the effective pair against the stored values.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    min_select: int | None = Field(default=None, ge=0, le=policies.MAX_MODIFIER_OPTIONS_PER_GROUP)
    max_select: int | None = Field(default=None, ge=1, le=policies.MAX_MODIFIER_OPTIONS_PER_GROUP)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _normalized_name(value) if value is not None else None

    @model_validator(mode="after")
    def _semantics(self) -> "ModifierGroupUpdate":
        for field in ("name", "min_select"):
            if field in self.model_fields_set and getattr(self, field) is None:
                msg = f"{field} cannot be null"
                raise ValueError(msg)
        if (
            "min_select" in self.model_fields_set
            and "max_select" in self.model_fields_set
            and self.min_select is not None
            and self.max_select is not None
            and self.min_select > self.max_select
        ):
            msg = "min_select cannot exceed max_select"
            raise ValueError(msg)
        return self


class ModifierGroupReorder(BaseModel):
    """Full-set group reorder: every group id of the item, in order."""

    model_config = ConfigDict(extra="forbid")

    ordered_group_ids: list[uuid.UUID] = Field(
        min_length=1, max_length=policies.MAX_MODIFIER_GROUPS_PER_ITEM
    )

    @field_validator("ordered_group_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return _unique_ids(value)


class ModifierOptionCreate(BaseModel):
    """Create an option (appended; starts available)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    price_delta_minor: int = Field(default=0, ge=0, le=policies.MAX_PRICE_MINOR)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _normalized_name(value)


class ModifierOptionUpdate(BaseModel):
    """Partial option update; availability rides this PATCH (D3)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    price_delta_minor: int | None = Field(default=None, ge=0, le=policies.MAX_PRICE_MINOR)
    is_available: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _normalized_name(value) if value is not None else None

    @model_validator(mode="after")
    def _no_nulls(self) -> "ModifierOptionUpdate":
        for field in ("name", "price_delta_minor", "is_available"):
            if field in self.model_fields_set and getattr(self, field) is None:
                msg = f"{field} cannot be null"
                raise ValueError(msg)
        return self


class ModifierOptionReorder(BaseModel):
    """Full-set option reorder within one group."""

    model_config = ConfigDict(extra="forbid")

    ordered_option_ids: list[uuid.UUID] = Field(
        min_length=1, max_length=policies.MAX_MODIFIER_OPTIONS_PER_GROUP
    )

    @field_validator("ordered_option_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return _unique_ids(value)


class ModifierOptionView(BaseModel):
    """One option (administrative projection)."""

    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    price_delta_minor: int
    is_available: bool
    position: int
    created_at: datetime
    updated_at: datetime


class ModifierGroupView(BaseModel):
    """One group with its ordered options and computed satisfiability.

    ``active_option_count`` and ``is_satisfiable`` are computed from the
    authoritative post-mutation state (D5) — never stored.
    """

    id: uuid.UUID
    item_id: uuid.UUID
    name: str
    min_select: int
    max_select: int | None
    position: int
    active_option_count: int
    is_satisfiable: bool
    options: list[ModifierOptionView]
    created_at: datetime
    updated_at: datetime


class ModifierGroupsView(BaseModel):
    """The bounded per-item modifier tree (D2): ordered groups."""

    item_id: uuid.UUID
    groups: list[ModifierGroupView]
