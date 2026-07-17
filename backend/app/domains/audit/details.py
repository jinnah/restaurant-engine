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


class TenantCreatedDetails(AuditDetails):
    """A restaurant was created (starts in provisioning)."""

    slug: str


class TenantStatusChangedDetails(AuditDetails):
    """A restaurant lifecycle transition (M2B)."""

    previous_status: str
    new_status: str
