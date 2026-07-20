"""Catalog product-policy constants and name normalization (M3A, ADR-017).

Centralized code policy (rulings R1/R2): uniform across tenants, not
deployment-tunable, and not tenant-configurable in M3. Count-dependent
enforcement runs in the service under the business-row lock; a CHECK
cannot count rows. The approved M3B/M3C bounds (600 modifier groups and
3000 options per business; media limits) are recorded in ADR-017 and land
with their sub-milestones.
"""

import unicodedata

# --- Count limits (R2), enforced under the business-row lock -----------------
MAX_CATEGORIES_PER_BUSINESS = 50
MAX_ITEMS_PER_BUSINESS = 300
MAX_ITEMS_PER_CATEGORY = 100
MAX_DIETARY_TAGS_PER_ITEM = 3

# --- Modifier limits (M3B, ADR-017) ------------------------------------------
# MAX_MODIFIER_OPTIONS_PER_GROUP is mirrored by the literal 30 in the
# modifier_groups selection-range CHECKs (a pinned test keeps them equal).
MAX_MODIFIER_GROUPS_PER_ITEM = 10
MAX_MODIFIER_GROUPS_PER_BUSINESS = 600
MAX_MODIFIER_OPTIONS_PER_GROUP = 30
MAX_MODIFIER_OPTIONS_PER_BUSINESS = 3000

# --- Featured policy (R1) ----------------------------------------------------
# Counts every item with is_featured = true, hidden included; hiding never
# clears the flag; exceeding returns 409 `conflict` with details.limit.
MAX_FEATURED_ITEMS = 6

# --- Value bounds (R2; price bound per the post-review F1 ruling) ------------
MAX_NAME_LENGTH = 120
MAX_CATEGORY_DESCRIPTION_LENGTH = 500
MAX_ITEM_DESCRIPTION_LENGTH = 1000
# Contextual image alt text on a menu item (M3C attachment); mirrors the
# menu_items DB CHECK. The bound matches media.policies.MAX_IMAGE_ALT_LENGTH
# (a pinned test keeps them equal).
MAX_IMAGE_ALT_LENGTH = 300
# Approved item-price range: 0 <= price_minor <= 10,000,000 minor units
# (ADR-017). The bound (a) keeps public and audit representations bounded,
# (b) prevents unrealistic or accidental extreme values, (c) still permits
# every realistic restaurant and catering price, and (d) is a product-policy
# constant, not a tenant setting. Enforced in the schemas (422) AND by the
# named database CHECKs (price_nonnegative, price_maximum); the audit price
# extractor shares this constant so no valid price can ever fall out of a
# projection.
MAX_PRICE_MINOR = 10_000_000


def is_group_satisfiable(min_select: int, max_select: int | None, active_count: int) -> bool:
    """The ruled satisfiability formula (ADR-017 D5) — computed, never stored.

    A group is satisfiable when at least one available option exists, the
    minimum can be met, and a finite maximum does not exceed the available
    options (docs/03: max cannot exceed selectable active options unless
    NULL/unlimited). Report-only in M3B: never a write gate.
    """
    if active_count < 1:
        return False
    if min_select > active_count:
        return False
    return max_select is None or max_select <= active_count


def normalize_name(value: str) -> str:
    """Canonical display form of a catalog name (ruling R6).

    Trim, collapse every internal whitespace run to one space, then Unicode
    NFC. Case is preserved for display; case-insensitive uniqueness is the
    database expression index on ``lower(name)`` (full Unicode case-folding
    beyond ``lower()`` is documented as not attempted — Bengali, the launch
    market's script, is caseless).
    """
    return unicodedata.normalize("NFC", " ".join(value.split()))
