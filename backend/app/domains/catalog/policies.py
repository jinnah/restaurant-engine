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

# --- Featured policy (R1) ----------------------------------------------------
# Counts every item with is_featured = true, hidden included; hiding never
# clears the flag; exceeding returns 409 `conflict` with details.limit.
MAX_FEATURED_ITEMS = 6

# --- Value bounds (R2; price bound per the post-review F1 ruling) ------------
MAX_NAME_LENGTH = 120
MAX_CATEGORY_DESCRIPTION_LENGTH = 500
MAX_ITEM_DESCRIPTION_LENGTH = 1000
# Approved item-price range: 0 <= price_minor <= 10,000,000 minor units
# (ADR-017). The bound (a) keeps public and audit representations bounded,
# (b) prevents unrealistic or accidental extreme values, (c) still permits
# every realistic restaurant and catering price, and (d) is a product-policy
# constant, not a tenant setting. Enforced in the schemas (422) AND by the
# named database CHECKs (price_nonnegative, price_maximum); the audit price
# extractor shares this constant so no valid price can ever fall out of a
# projection.
MAX_PRICE_MINOR = 10_000_000


def normalize_name(value: str) -> str:
    """Canonical display form of a catalog name (ruling R6).

    Trim, collapse every internal whitespace run to one space, then Unicode
    NFC. Case is preserved for display; case-insensitive uniqueness is the
    database expression index on ``lower(name)`` (full Unicode case-folding
    beyond ``lower()`` is documented as not attempted — Bengali, the launch
    market's script, is caseless).
    """
    return unicodedata.normalize("NFC", " ".join(value.split()))
