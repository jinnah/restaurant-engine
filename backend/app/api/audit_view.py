"""Safe audit-detail projection (M2D, ADR-014 correction D + binding
clarification).

Stored ``details`` JSON is **never** trusted as an API-safe projection —
not even though write-time schemas and denylist tests exist. Every
recognized action maps to a **typed** read-time projection: each permitted
key has a value extractor that admits only the expected primitive type
within bounds. Values are never copied verbatim, so a malicious or
malformed stored value (for example a nested object smuggled into
``reason``) can never reach a response. Unknown actions project to
``None``; extra stored keys are dropped; a final sensitive-key sweep
removes anything token/password/session/cookie/authorization/secret-like
as defense-in-depth.

Composition-layer placement keeps authorization out of the audit domain
(no identity → audit → identity cycle).
"""

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime

from pydantic import BaseModel

from app.domains.audit.actions import AuditAction
from app.domains.audit.models import AuditEvent
from app.domains.catalog.policies import MAX_PRICE_MINOR
from app.domains.media.policies import MAX_ASSET_OUTPUT_BYTES

_MAX_STRING = 320  # longest legitimate detail value (emails are <= 254)

# Fragments that may never appear in a projected detail key, regardless of
# what a (mistaken) registry entry might one day permit.
_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "token",
    "hash",
    "secret",
    "cookie",
    "credential",
    "authorization",
    "session",
)

_Extractor = Callable[[object], str | int | None]


def _short_str(value: object) -> str | None:
    """Admit only a bounded plain string — never nested structures."""
    if isinstance(value, str) and 0 < len(value) <= _MAX_STRING:
        return value
    return None


def _small_int(value: object) -> int | None:
    """Admit only a bounded plain int (bool is not an int here)."""
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000:
        return value
    return None


def _choice(allowed: frozenset[str]) -> "_Extractor":
    """Closed-set string extractor (M3B): admits only an exact member.

    Used for the modifier maximum-selection mode and option availability,
    so those facts stay bounded strings — the projection value union
    remains ``str | int`` with no boolean (D6 correction).
    """

    def _extract(value: object) -> str | None:
        if isinstance(value, str) and value in allowed:
            return value
        return None

    return _extract


_MODE_CHOICE = _choice(frozenset({"finite", "unlimited"}))
_AVAILABILITY_CHOICE = _choice(frozenset({"available", "unavailable"}))
# M3C media closed-set extractors.
_SOURCE_FORMAT_CHOICE = _choice(frozenset({"jpeg", "png", "webp"}))
_STATUS_CHOICE = _choice(frozenset({"pending", "active"}))
_TRIGGER_CHOICE = _choice(frozenset({"pending_ttl_sweep"}))
_CHANGE_CHOICE = _choice(frozenset({"attached", "replaced", "cleared", "alt_updated"}))
_ALT_CHANGED_CHOICE = _choice(frozenset({"changed", "unchanged"}))


def _byte_int(value: object) -> int | None:
    """Admit an encoded-byte size within the per-asset output bound (M3C)."""
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= MAX_ASSET_OUTPUT_BYTES
    ):
        return value
    return None


def _price_int(value: object) -> int | None:
    """Admit an integer minor-unit price within the approved range.

    Shares the catalog policy constant (ADR-017 F1 ruling: 0..10,000,000),
    so every price the schemas and the DB CHECK accept is faithfully
    retained by the projection — a valid price can never silently drop out
    of the audit response.
    """
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_PRICE_MINOR:
        return value
    return None


# Per-action allowlists with typed extractors. Business-scoped responses may
# only ever project a subset of the platform projection; today the
# business-visible actions share the same field sets, and auth/platform
# actions never appear in business scope at all (query-level exclusion).
_PROJECTIONS: dict[str, dict[str, _Extractor]] = {
    AuditAction.AUTH_LOGIN_SUCCEEDED.value: {},
    AuditAction.AUTH_LOGOUT.value: {},
    AuditAction.AUTH_LOGIN_FAILED.value: {
        "email_normalized": _short_str,
        "reason": _short_str,
    },
    AuditAction.AUTH_LOGIN_THROTTLED.value: {
        "email_normalized": _short_str,
        "failed_login_count": _small_int,
        "backoff_seconds": _small_int,
    },
    AuditAction.USER_PLATFORM_ADMIN_CREATED.value: {"email_normalized": _short_str},
    AuditAction.BUSINESS_CREATED.value: {"slug": _short_str},
    AuditAction.BUSINESS_ACTIVATED.value: {
        "previous_status": _short_str,
        "new_status": _short_str,
    },
    AuditAction.BUSINESS_SUSPENDED.value: {
        "previous_status": _short_str,
        "new_status": _short_str,
    },
    AuditAction.BUSINESS_REACTIVATED.value: {
        "previous_status": _short_str,
        "new_status": _short_str,
    },
    AuditAction.BUSINESS_CLOSED.value: {
        "previous_status": _short_str,
        "new_status": _short_str,
    },
    AuditAction.BUSINESS_INVITATION_ISSUED.value: {
        "email_normalized": _short_str,
        "role": _short_str,
    },
    AuditAction.BUSINESS_INVITATION_REVOKED.value: {
        "email_normalized": _short_str,
        "role": _short_str,
    },
    AuditAction.BUSINESS_INVITATION_ACCEPTED.value: {
        "email_normalized": _short_str,
        "role": _short_str,
    },
    AuditAction.BUSINESS_ENTITLEMENT_GRANTED.value: {"feature_key": _short_str},
    AuditAction.BUSINESS_ENTITLEMENT_REVOKED.value: {"feature_key": _short_str},
    AuditAction.AUTH_PASSWORD_RESET_ISSUED.value: {"email_normalized": _short_str},
    AuditAction.AUTH_PASSWORD_RESET_COMPLETED.value: {"email_normalized": _short_str},
    # M3A catalog (ADR-017): bounded names, closed-set changed_fields
    # summaries, integer minor-unit prices via the dedicated price
    # extractor (shares MAX_PRICE_MINOR, so a legitimate price can never
    # truncate away).
    AuditAction.CATALOG_CATEGORY_CREATED.value: {"name": _short_str},
    AuditAction.CATALOG_CATEGORY_UPDATED.value: {
        "name": _short_str,
        "changed_fields": _short_str,
    },
    AuditAction.CATALOG_CATEGORY_DELETED.value: {"name": _short_str},
    AuditAction.CATALOG_CATEGORIES_REORDERED.value: {"count": _small_int},
    AuditAction.CATALOG_ITEM_CREATED.value: {
        "name": _short_str,
        "category_id": _short_str,
        "price_minor": _price_int,
    },
    AuditAction.CATALOG_ITEM_UPDATED.value: {
        "changed_fields": _short_str,
        "price_minor_old": _price_int,
        "price_minor_new": _price_int,
        "category_id": _short_str,
    },
    AuditAction.CATALOG_ITEM_DELETED.value: {
        "name": _short_str,
        "category_id": _short_str,
    },
    AuditAction.CATALOG_ITEMS_REORDERED.value: {"count": _small_int},
    AuditAction.CATALOG_ITEM_AVAILABILITY_CHANGED.value: {"availability": _short_str},
    # M3B modifiers (ADR-017): explicit max-selection mode; closed-set
    # strings via _choice; bounded ints via _small_int/_price_int.
    AuditAction.CATALOG_MODIFIER_GROUP_CREATED.value: {
        "name": _short_str,
        "item_id": _short_str,
        "min_select": _small_int,
        "max_select_mode": _MODE_CHOICE,
        "max_select": _small_int,
    },
    AuditAction.CATALOG_MODIFIER_GROUP_UPDATED.value: {
        "changed_fields": _short_str,
        "min_select_old": _small_int,
        "min_select_new": _small_int,
        "max_select_mode_old": _MODE_CHOICE,
        "max_select_mode_new": _MODE_CHOICE,
        "max_select_old": _small_int,
        "max_select_new": _small_int,
    },
    AuditAction.CATALOG_MODIFIER_GROUP_DELETED.value: {
        "name": _short_str,
        "item_id": _short_str,
        "option_count": _small_int,
    },
    AuditAction.CATALOG_MODIFIER_GROUPS_REORDERED.value: {"count": _small_int},
    AuditAction.CATALOG_MODIFIER_OPTION_CREATED.value: {
        "name": _short_str,
        "group_id": _short_str,
        "price_delta_minor": _price_int,
    },
    AuditAction.CATALOG_MODIFIER_OPTION_UPDATED.value: {
        "changed_fields": _short_str,
        "price_delta_minor_old": _price_int,
        "price_delta_minor_new": _price_int,
        "availability_old": _AVAILABILITY_CHOICE,
        "availability_new": _AVAILABILITY_CHOICE,
    },
    AuditAction.CATALOG_MODIFIER_OPTION_DELETED.value: {
        "name": _short_str,
        "group_id": _short_str,
    },
    AuditAction.CATALOG_MODIFIER_OPTIONS_REORDERED.value: {"count": _small_int},
    # M3C media (ADR-017): closed-set format/status/trigger/change via
    # _choice; bounded ints; no key/path/checksum/alt-text is ever
    # projectable because none is ever stored.
    AuditAction.MEDIA_ASSET_UPLOADED.value: {
        "source_format": _SOURCE_FORMAT_CHOICE,
        "width": _small_int,
        "height": _small_int,
        "byte_size": _byte_int,
        "variant_count": _small_int,
    },
    AuditAction.MEDIA_ASSET_DELETED.value: {
        "status": _STATUS_CHOICE,
        "variant_count": _small_int,
    },
    AuditAction.MEDIA_ASSET_EXPIRED.value: {
        "trigger": _TRIGGER_CHOICE,
        "variant_count": _small_int,
    },
    AuditAction.CATALOG_ITEM_IMAGE_CHANGED.value: {
        "change": _CHANGE_CHOICE,
        "media_id_old": _short_str,
        "media_id_new": _short_str,
        "alt_text_changed": _ALT_CHANGED_CHOICE,
    },
}


def project_details(action: str, stored: object) -> dict[str, str | int] | None:
    """The API-safe projection of one event's stored details.

    Unregistered action → ``None``. Non-mapping stored payload → ``None``.
    Only registry keys are read; only conforming primitive values pass; the
    sensitive-key sweep is a final structural guarantee.
    """
    allowlist = _PROJECTIONS.get(action)
    if allowlist is None or not allowlist:
        return None
    if not isinstance(stored, Mapping):
        return None
    projected: dict[str, str | int] = {}
    for key, extract in allowlist.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
            continue  # defense-in-depth: a registry mistake stays unexploitable
        value = extract(stored.get(key))
        if value is not None:
            projected[key] = value
    return projected or None


class AuditEventSummary(BaseModel):
    """One immutable audit event (read-only projection)."""

    id: int
    occurred_at: datetime
    action: str
    business_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    correlation_id: str | None
    target_type: str | None
    target_id: str | None
    details: dict[str, str | int] | None


class AuditEventPage(BaseModel):
    """Cursor page (``id DESC``); ``next_before_id`` feeds the next request."""

    items: list[AuditEventSummary]
    next_before_id: int | None


def build_page(events: list[AuditEvent], *, limit: int) -> AuditEventPage:
    items = [
        AuditEventSummary(
            id=event.id,
            occurred_at=event.occurred_at,
            action=event.action,
            business_id=event.business_id,
            actor_user_id=event.actor_user_id,
            correlation_id=event.correlation_id,
            target_type=event.target_type,
            target_id=event.target_id,
            details=project_details(event.action, event.details),
        )
        for event in events
    ]
    next_before_id = items[-1].id if len(items) == limit and items else None
    return AuditEventPage(items=items, next_before_id=next_before_id)
