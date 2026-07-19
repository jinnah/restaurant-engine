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
