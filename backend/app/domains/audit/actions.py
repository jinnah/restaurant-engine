"""Audit action registry (M2A).

Append-only, like the error-code registry (ADR-008): actions are never
renamed or reused, and an action is added only in the change that first
records it. The registry is code, not a database CHECK, so adding an
action is not a migration.
"""

from enum import StrEnum


class AuditAction(StrEnum):
    """Machine-readable audit event names (append-only)."""

    AUTH_LOGIN_SUCCEEDED = "auth.login_succeeded"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGIN_THROTTLED = "auth.login_throttled"
    AUTH_LOGOUT = "auth.logout"
    USER_PLATFORM_ADMIN_CREATED = "user.platform_admin_created"
    # M2B: business lifecycle (ADR-012: Business is the tenant aggregate).
    BUSINESS_CREATED = "business.created"
    BUSINESS_ACTIVATED = "business.activated"
    BUSINESS_SUSPENDED = "business.suspended"
    BUSINESS_REACTIVATED = "business.reactivated"
    BUSINESS_CLOSED = "business.closed"
