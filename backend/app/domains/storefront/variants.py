"""Design-variant registry (M4A, ADR-020).

Append-only and code-owned, like the dietary-tag, feature-key, and
audit-action registries: a variant is added in the change that first ships
its renderer, and the registry is code — not a DB CHECK — so adding one is
not a migration.

Design assignment is **platform-governed** (blueprint §12.3): the platform
controls structural variants; restaurant users never submit one. The
selected variant is stored on the version row (ADR-020 D4), never on
``businesses``, so a published or archived version keeps the variant it was
rendered with and historical rendering stays stable.

Exactly one variant ships in M4A. That is deliberate: a variant is a
*renderer* contract, and no storefront renderer exists until M4D. Naming
further variants now would publish structure nothing can render. Writes
reject unknown values; reads are fail-closed, so a stored value missing
from this registry is never treated as valid.
"""

from enum import StrEnum


class DesignVariant(StrEnum):
    """Platform-curated structural design variants (append-only)."""

    CLASSIC = "classic"


# The explicit platform default. Every initial draft starts here unless a
# platform administrator assigns another variant (the M4B command); there is
# no implicit "first member of the enum" rule to drift.
PLATFORM_DEFAULT_VARIANT: DesignVariant = DesignVariant.CLASSIC

_KNOWN_VALUES = frozenset(variant.value for variant in DesignVariant)


def is_known_variant(value: str) -> bool:
    """True when ``value`` is a registered design variant."""
    return value in _KNOWN_VALUES
