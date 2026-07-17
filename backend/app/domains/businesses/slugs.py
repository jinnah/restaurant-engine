"""Canonical Business slug policy (M2C, ADR-013).

Single source of truth for slug **shape** and the **reserved-label** set,
consumed by both Business creation (schema validation) and public host
resolution. Sharing one policy is the invariant: a Business must never be
created with a slug that its subdomain could never resolve (for example a
label reserved for platform infrastructure).
"""

import re

# 3-63 chars, lowercase alphanumeric with internal hyphens, no edge hyphen.
# Matches the ``ck_businesses_slug_canonical`` database CHECK.
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")

# Labels reserved for platform infrastructure hosts under the platform base
# domain. A tenant may never claim one. Deliberately minimal — only labels
# backed by real or already-approved infrastructure (ADR-013):
#   api   — the API host
#   admin — the control-center host (platform + business administration)
#   www   — the canonical / marketing host
RESERVED_SLUGS = frozenset({"api", "admin", "www"})


def is_slug_shaped(value: str) -> bool:
    """True when ``value`` already satisfies the canonical slug shape."""
    return SLUG_PATTERN.match(value) is not None


def is_reserved(slug: str) -> bool:
    """True when ``slug`` is reserved for platform infrastructure."""
    return slug in RESERVED_SLUGS
