"""Business API schemas (M2B).

Command schemas reject unknown fields (blueprint §11.3; approved point 8).
Response schemas are explicit — never serialized ORM objects.
"""

import uuid
import zoneinfo
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.domains.businesses.slugs import is_reserved, is_slug_shaped
from app.domains.identity.policies import Role


class BusinessCreate(BaseModel):
    """Platform command to create a business (starts in provisioning)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=63)
    timezone: str = "America/New_York"
    currency: str = "USD"

    @field_validator("slug")
    @classmethod
    def _canonical_slug(cls, value: str) -> str:
        # Canonicalize before the checks so mixed-case / padded input is
        # accepted and stored in one canonical (lowercase) form. Shape and
        # the reserved-label set come from the shared slug policy, so
        # creation and public resolution can never diverge (ADR-013).
        canonical = value.strip().lower()
        if not is_slug_shaped(canonical):
            msg = "slug must be 3-63 chars, lowercase letters/digits/hyphens, no edge hyphen"
            raise ValueError(msg)
        if is_reserved(canonical):
            # Generic message: does not enumerate the reserved set.
            msg = "slug is reserved"
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


class BusinessSummary(BaseModel):
    """Public representation of a business (never the ORM object)."""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    timezone: str
    currency: str
    created_at: datetime
    updated_at: datetime


class BusinessPage(BaseModel):
    """A bounded page of businesses for the platform catalog."""

    items: list[BusinessSummary]
    total: int
    limit: int
    offset: int


class PublicSiteSummary(BaseModel):
    """Minimal public projection returned for a resolved active business
    (M2C, ADR-013).

    Deliberately narrow: a 200 already proves the business is active, so no
    ``status`` field is needed, and no id/timestamps/management data are
    exposed on the unauthenticated surface.
    """

    name: str
    slug: str
    timezone: str
    currency: str


PaginationLimit = Annotated[int, Field(ge=1, le=100)]
PaginationOffset = Annotated[int, Field(ge=0)]


class InvitationCreate(BaseModel):
    """Command to invite a member (business-scoped or platform route)."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    role: Role


class InvitationIssueResponse(BaseModel):
    """One-time issuance result (ADR-014).

    ``token`` is the raw secret, returned exactly once to the authorized
    issuer for out-of-band delivery — never a URL, never stored, never
    logged, never shown again.
    """

    token: str
    invitation_id: uuid.UUID
    expires_at: datetime
    email: str
    role: Role


class InvitationSummary(BaseModel):
    """One pending invitation (operational list; no token, no hash)."""

    invitation_id: uuid.UUID
    email: str
    role: Role
    created_at: datetime
    expires_at: datetime
    state: Literal["pending", "expired"]
    invited_by_user_id: uuid.UUID


class InvitationPage(BaseModel):
    items: list[InvitationSummary]
    total: int
    limit: int
    offset: int


class InvitationPreviewRequest(BaseModel):
    """Public preview lookup — the token travels in the body, never a URL."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)


class InvitationPreviewResponse(BaseModel):
    """PII-minimized accept-page context (correction E)."""

    business_name: str
    role: Role
    email_hint: str


class InvitationAcceptRequest(BaseModel):
    """Public acceptance creating a new account (no auto-login)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("display_name")
    @classmethod
    def _trim_display_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            msg = "display_name must not be blank"
            raise ValueError(msg)
        return trimmed


class InvitationAcceptExistingRequest(BaseModel):
    """Authenticated acceptance adding a membership to the caller."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)


class InvitationAcceptedResponse(BaseModel):
    status: Literal["accepted"]
    business_id: uuid.UUID
    email: str
    role: Role


class InvitationRevokedResponse(BaseModel):
    status: Literal["revoked"]
