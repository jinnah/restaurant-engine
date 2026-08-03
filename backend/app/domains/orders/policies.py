"""Orders policy constants and text normalization (M6A, ADR-026).

Centralized code policy, like ``catalog.policies`` and ``hours.policies``:
uniform across tenants, not deployment-tunable. Bounds are enforced by
the schemas (422) and, where a CHECK can express them, by the database.

Money is integer minor units everywhere (blueprint §3.5). The total
guard is defence in depth far inside BIGINT range: the per-item price
cap (catalog F1: 10,000,000 minor units), the quantity cap, and the
line cap already bound any honest total well below it.
"""

import unicodedata

# --- Cart bounds --------------------------------------------------------------
MAX_LINES_PER_ORDER = 30
MIN_LINE_QUANTITY = 1
MAX_LINE_QUANTITY = 50
# 30 lines x 50 qty x (10,000,000 + generous option deltas) stays far
# below this; anything at the guard is corrupt input, not a real order.
MAX_TOTAL_MINOR = 4_000_000_000

# --- Customer fields (blueprint §7.7: bounded plain text, never
# operational instructions to the system) ------------------------------------
MAX_CUSTOMER_NAME_LENGTH = 120
MAX_CUSTOMER_PHONE_LENGTH = 40
MAX_CUSTOMER_EMAIL_LENGTH = 254
MAX_ITEM_INSTRUCTIONS_LENGTH = 200
MAX_ORDER_INSTRUCTIONS_LENGTH = 500

# --- Tracking token (ruling D4: the M2D token pattern) ------------------------
# 256-bit random token, stored only as a SHA-256 hex digest; returned
# exactly once, in the placement response.
TRACKING_TOKEN_BYTES = 32

# --- Idempotency (ruling D2) ---------------------------------------------------
IDEMPOTENCY_OPERATION_PLACE = "order.place"

# --- Public slot listing (M6B consumes; the bound is policy now so the
# checkout's scheduled-slot validation and the listing share it) ---------------
MAX_PUBLIC_SLOTS = 100

# --- The operational surface (M7A, ADR-027 rulings D6/D11) --------------------
LIST_DEFAULT_PAGE_SIZE = 50
LIST_MAX_PAGE_SIZE = 100
LIST_QUERY_MAX_LENGTH = 80
METRICS_POPULAR_ITEMS = 5
# Today's display constants (real data arrives with payments / channels).
PAYMENT_DISPLAY = "pay_at_pickup"
SOURCE_DISPLAY = "online"


def normalize_line(value: str) -> str:
    """Canonical single-line text: trim, collapse whitespace, Unicode NFC.

    Restated locally (the hours/catalog convention) so orders imports no
    other domain for text policy.
    """
    return unicodedata.normalize("NFC", " ".join(value.split()))


def normalize_block(value: str) -> str:
    """Canonical multi-line text: NFC, trimmed, blank runs collapsed.

    Order- and item-level instructions keep paragraph breaks the customer
    typed; interior whitespace on each line collapses like a line.
    """
    lines = [" ".join(line.split()) for line in value.split("\n")]
    collapsed: list[str] = []
    for line in lines:
        if line == "" and (not collapsed or collapsed[-1] == ""):
            continue
        collapsed.append(line)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return unicodedata.normalize("NFC", "\n".join(collapsed))


def has_control_characters(value: str, *, allow_newline: bool = False) -> bool:
    """True when ``value`` carries a control character (category Cc).

    Rejected rather than stripped (the storefront reason): a control
    character in customer text is a paste accident or smuggling, and
    refusing keeps stored text exactly what was visible.
    """
    for char in value:
        if allow_newline and char == "\n":
            continue
        if unicodedata.category(char) == "Cc":
            return True
    return False
