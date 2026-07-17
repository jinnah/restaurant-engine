"""Tenant API schemas (M2B).

Command schemas reject unknown fields (blueprint §11.3; approved point 8).
Response schemas are explicit — never serialized ORM objects.
"""

import re
import uuid
import zoneinfo
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")


class RestaurantCreate(BaseModel):
    """Platform command to create a restaurant (starts in provisioning)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=63)
    timezone: str = "America/New_York"
    currency: str = "USD"

    @field_validator("slug")
    @classmethod
    def _canonical_slug(cls, value: str) -> str:
        # Canonicalize before the regex check so mixed-case / padded input
        # is accepted and stored in one canonical (lowercase) form.
        canonical = value.strip().lower()
        if not _SLUG_PATTERN.match(canonical):
            msg = "slug must be 3-63 chars, lowercase letters/digits/hyphens, no edge hyphen"
            raise ValueError(msg)
        return canonical

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            msg = "name must not be blank"
            raise ValueError(msg)
        return trimmed

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        if value not in zoneinfo.available_timezones():
            msg = f"unknown IANA timezone: {value!r}"
            raise ValueError(msg)
        return value

    @field_validator("currency")
    @classmethod
    def _iso4217_shape(cls, value: str) -> str:
        upper = value.strip().upper()
        if len(upper) != 3 or not upper.isalpha():
            msg = "currency must be a 3-letter ISO 4217 code"
            raise ValueError(msg)
        return upper


class EmptyCommand(BaseModel):
    """Body for no-argument lifecycle commands.

    Present so an unexpected JSON field is rejected (422) rather than
    silently ignored (approved amendment 3): a lifecycle POST carries no
    data, but it must still be strict about what it accepts.
    """

    model_config = ConfigDict(extra="forbid")


class RestaurantSummary(BaseModel):
    """Public representation of a restaurant (never the ORM object)."""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    timezone: str
    currency: str
    created_at: datetime
    updated_at: datetime


class RestaurantPage(BaseModel):
    """A bounded page of restaurants for the platform catalog."""

    items: list[RestaurantSummary]
    total: int
    limit: int
    offset: int


PaginationLimit = Annotated[int, Field(ge=1, le=100)]
PaginationOffset = Annotated[int, Field(ge=0)]
