"""Typed detail schemas for audit events (M2A, approved review item R13).

Every recordable action has exactly one detail schema here (or ``None``).
Call sites can not pass free-form dictionaries: the recorder accepts only
these models, so the set of keys that can ever reach the ``details`` JSONB
column is closed, reviewable, and provably free of secrets
(tests/unit/test_audit_details.py enforces the denylist).

Emails of platform users (owners, staff, admins) are deliberately allowed:
they are operational identifiers needed for security forensics, not
customer data (docs/04 privacy-minimization).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AuditDetails(BaseModel):
    """Base class for all audit detail payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LoginFailedDetails(AuditDetails):
    """Why a login attempt was rejected (never disclosed to the client)."""

    email_normalized: str
    reason: Literal["unknown_email", "invalid_password", "inactive_account"]


class LoginThrottledDetails(AuditDetails):
    """An attempt arrived inside the account's backoff window."""

    email_normalized: str
    failed_login_count: int
    backoff_seconds: int


class PlatformAdminCreatedDetails(AuditDetails):
    """A platform administrator account was created via the bootstrap CLI."""

    email_normalized: str


class BusinessCreatedDetails(AuditDetails):
    """A business was created (starts in provisioning)."""

    slug: str


class BusinessStatusChangedDetails(AuditDetails):
    """A business lifecycle transition (M2B)."""

    previous_status: str
    new_status: str


class InvitationDetails(AuditDetails):
    """A membership invitation was issued, revoked, or accepted (M2D).

    Never the token or its hash — only the invited identity and role.
    """

    email_normalized: str
    role: str


class EntitlementDetails(AuditDetails):
    """A product feature was granted to or revoked from a business (M2D)."""

    feature_key: str


class PasswordResetDetails(AuditDetails):
    """A recovery token was issued or redeemed (M2D).

    Never the token or its hash. The issuing administrator is the event's
    actor; the affected account is the target and its email is recorded
    here (platform-user emails are allowed operational identifiers).
    """

    email_normalized: str


# --- Catalog (M3A, ADR-017) --------------------------------------------------
#
# Bounded values only: normalized names are <= 120 chars; changed_fields is
# a comma-joined, sorted string drawn from a closed field-name set (a plain
# bounded string, so the read-time projection's primitive extractors apply
# unchanged); prices are ints <= MAX_PRICE_MINOR. Free-text descriptions
# never enter audit payloads.


class CatalogCategoryDetails(AuditDetails):
    """A menu category was created or deleted."""

    name: str


class CatalogCategoryUpdatedDetails(AuditDetails):
    """A menu category changed; which fields is the closed-set summary."""

    name: str
    changed_fields: str


class CatalogReorderDetails(AuditDetails):
    """A full-set reorder ran (categories or items); count of rows."""

    count: int


class CatalogItemCreatedDetails(AuditDetails):
    """A menu item was created."""

    name: str
    category_id: str
    price_minor: int


class CatalogItemUpdatedDetails(AuditDetails):
    """A menu item changed.

    ``price_minor_old``/``price_minor_new`` are present exactly when the
    price changed (queryable price history); ``category_id`` is the
    destination exactly when the item moved.
    """

    changed_fields: str
    price_minor_old: int | None = None
    price_minor_new: int | None = None
    category_id: str | None = None


class CatalogItemDeletedDetails(AuditDetails):
    """A menu item was deleted."""

    name: str
    category_id: str


class CatalogItemAvailabilityDetails(AuditDetails):
    """The staff-reachable "sold out today" toggle changed state."""

    availability: Literal["available", "sold_out"]
