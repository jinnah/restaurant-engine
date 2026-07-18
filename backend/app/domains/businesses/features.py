"""Product feature registry (M2D, ADR-014).

Append-only, like the audit-action and error-code registries: a feature
key is added in the change that first ships its capability. The registry
is code, not a DB CHECK, so adding a feature is not a migration.

Entitlements answer "which product capability does this Business have
enabled" — deliberately separate from identity capabilities ("what may
this actor do"). Neither implies the other. Reads are fail-closed: a
stored key missing from this registry is never surfaced as enabled
(``entitlements.get_effective_features``).
"""

from enum import StrEnum


class FeatureKey(StrEnum):
    """Platform product features assignable to a business (append-only).

    Seeded with exactly ``online_ordering`` (approved M2 decision); its
    enforcement arrives with checkout (M6). Catalog/storefront, SMS,
    Facebook publishing, and the AI assistant register here in their own
    milestones.
    """

    ONLINE_ORDERING = "online_ordering"


def is_known_feature(value: str) -> bool:
    """True when ``value`` is a registered feature key."""
    return value in _KNOWN_VALUES


_KNOWN_VALUES = frozenset(key.value for key in FeatureKey)
