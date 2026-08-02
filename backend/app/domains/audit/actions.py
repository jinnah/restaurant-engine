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
    # M2D: onboarding, recovery, and entitlements (ADR-014).
    BUSINESS_INVITATION_ISSUED = "business.invitation_issued"
    BUSINESS_INVITATION_REVOKED = "business.invitation_revoked"
    BUSINESS_INVITATION_ACCEPTED = "business.invitation_accepted"
    BUSINESS_ENTITLEMENT_GRANTED = "business.entitlement_granted"
    BUSINESS_ENTITLEMENT_REVOKED = "business.entitlement_revoked"
    # S105 suppressions: these are event names, not credentials.
    AUTH_PASSWORD_RESET_ISSUED = "auth.password_reset_issued"  # noqa: S105
    AUTH_PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"  # noqa: S105
    # M3A: catalog core (ADR-017).
    CATALOG_CATEGORY_CREATED = "catalog.category_created"
    CATALOG_CATEGORY_UPDATED = "catalog.category_updated"
    CATALOG_CATEGORY_DELETED = "catalog.category_deleted"
    CATALOG_CATEGORIES_REORDERED = "catalog.categories_reordered"
    CATALOG_ITEM_CREATED = "catalog.item_created"
    CATALOG_ITEM_UPDATED = "catalog.item_updated"
    CATALOG_ITEM_DELETED = "catalog.item_deleted"
    CATALOG_ITEMS_REORDERED = "catalog.items_reordered"
    CATALOG_ITEM_AVAILABILITY_CHANGED = "catalog.item_availability_changed"
    # M3B: modifiers (ADR-017).
    CATALOG_MODIFIER_GROUP_CREATED = "catalog.modifier_group_created"
    CATALOG_MODIFIER_GROUP_UPDATED = "catalog.modifier_group_updated"
    CATALOG_MODIFIER_GROUP_DELETED = "catalog.modifier_group_deleted"
    CATALOG_MODIFIER_GROUPS_REORDERED = "catalog.modifier_groups_reordered"
    CATALOG_MODIFIER_OPTION_CREATED = "catalog.modifier_option_created"
    CATALOG_MODIFIER_OPTION_UPDATED = "catalog.modifier_option_updated"
    CATALOG_MODIFIER_OPTION_DELETED = "catalog.modifier_option_deleted"
    CATALOG_MODIFIER_OPTIONS_REORDERED = "catalog.modifier_options_reordered"
    # M3C: media (ADR-017).
    MEDIA_ASSET_UPLOADED = "media.asset_uploaded"
    MEDIA_ASSET_DELETED = "media.asset_deleted"
    MEDIA_ASSET_EXPIRED = "media.asset_expired"
    CATALOG_ITEM_IMAGE_CHANGED = "catalog.item_image_changed"
    # M4B: storefront composition (ADR-020 section 11). Deliberately no
    # storefront.draft_updated: it would fire on every save and turn
    # operational telemetry into administrative audit records.
    STOREFRONT_PUBLISHED = "storefront.published"
    STOREFRONT_VERSION_RESTORED = "storefront.version_restored"
    STOREFRONT_DESIGN_ASSIGNED = "storefront.design_assigned"
    # M5A: hours and fulfillment (ADR-025). Weekly and exception writes are
    # full-set replacements, so one event per command — never per row.
    BUSINESS_HOURS_UPDATED = "business.hours_updated"
    BUSINESS_SCHEDULE_EXCEPTION_SET = "business.schedule_exception_set"
    BUSINESS_SCHEDULE_EXCEPTION_REMOVED = "business.schedule_exception_removed"
    BUSINESS_FULFILLMENT_UPDATED = "business.fulfillment_updated"
    # D2: the platform timezone correction re-interprets every stored
    # local time, which is why it is audited with both values.
    BUSINESS_TIMEZONE_CHANGED = "business.timezone_changed"
    # M6A: guest ordering (ADR-026). Placement is a NULL-actor public
    # event; typed details carry ids and totals, never customer PII or
    # the tracking token.
    ORDER_PLACED = "order.placed"
