"""Hours policy constants and text normalization (M5A, ADR-025).

Centralized code policy, like ``catalog.policies`` and
``storefront.policies``: uniform across tenants, not deployment-tunable,
not tenant-configurable. Bounds are enforced by the schemas (422) and,
where a CHECK can express them, by the database.

Interval encoding (ruling D1): minutes from local midnight.
``opens_minute`` is 0-1439; ``closes_minute`` is 1-2879, where a value
above 1440 means the interval ends on the **following** local day. One
value carries the overnight case, so a CHECK can bound it and two
representations can never disagree.
"""

import unicodedata

MINUTES_PER_DAY = 1440

# --- Interval bounds (D1) ----------------------------------------------------
MIN_OPENS_MINUTE = 0
MAX_OPENS_MINUTE = MINUTES_PER_DAY - 1  # 23:59 — an interval must start today
MIN_CLOSES_MINUTE = 1
# opens <= 1439 and duration <= 1440 give 2879 as the latest expressible
# close (23:59 today + 24 h). 1440 exactly is midnight at the end of the day.
MAX_CLOSES_MINUTE = MAX_OPENS_MINUTE + MINUTES_PER_DAY
# A single interval never exceeds 24 hours; a business open around the
# clock on one day is exactly opens=0, closes=1440.
MAX_INTERVAL_MINUTES = MINUTES_PER_DAY

# Split service (lunch + dinner) is ordinary; four intervals per day is
# already unusual. The weekly full-set bound follows.
MAX_INTERVALS_PER_DAY = 4
MAX_WEEKLY_INTERVALS = 7 * MAX_INTERVALS_PER_DAY

# --- Exception window --------------------------------------------------------
# Writes are accepted only inside this window of the tenant's local
# calendar: a short backward reach for corrections, a bounded forward
# horizon (~18 months) so the table and the projection stay bounded. Past
# exceptions are retained as history, never pruned by M5.
EXCEPTION_PAST_WINDOW_DAYS = 30
EXCEPTION_FUTURE_WINDOW_DAYS = 550

# A label on structured data (ruling D6), e.g. "Closed for Eid" — never
# the freeform hours text blueprint §7.6 forbids.
MAX_NOTE_LENGTH = 120

# --- Availability scan bounds ------------------------------------------------
# The next-opening search is bounded so a business with no hours at all
# terminates with "none" rather than looping: a year plus enough slack to
# clear the exception horizon's edge cases.
NEXT_OPENING_SCAN_DAYS = 400

# --- Fulfillment bounds ------------------------------------------------------
MIN_LEAD_TIME_MINUTES = 0
MAX_LEAD_TIME_MINUTES = 1440
MIN_SLOT_INTERVAL_MINUTES = 5
MAX_SLOT_INTERVAL_MINUTES = 120
MIN_LAST_ORDER_MINUTES = 0
MAX_LAST_ORDER_MINUTES = 240
MIN_MAX_DAYS_AHEAD = 0
MAX_MAX_DAYS_AHEAD = 30
# M6A (ADR-026 D3): the per-slot order cap. NULL means unlimited — a cap
# is an explicit operational choice, so there is deliberately no numeric
# default. The setting lives here because hours owns throttling (docs/03
# domain map); counting and enforcement are the orders checkout's.
MIN_MAX_ORDERS_PER_SLOT = 1
MAX_MAX_ORDERS_PER_SLOT = 100

# --- Fulfillment defaults ----------------------------------------------------
# The registry defaults an absent ``fulfillment_settings`` row projects on
# read (the M4G-A compatibility mechanism: no backfill, first write
# materializes). ``pickup_enabled`` defaults False deliberately — ordering
# does not exist before M6, so no tenant advertises pickup facts it never
# chose; the remaining values are sensible starting points the owner sees
# when enabling.
DEFAULT_PICKUP_ENABLED = False
DEFAULT_ASAP_ENABLED = True
DEFAULT_LEAD_TIME_MINUTES = 20
DEFAULT_SLOT_INTERVAL_MINUTES = 15
DEFAULT_LAST_ORDER_MINUTES = 30
DEFAULT_MAX_DAYS_AHEAD = 0


def normalize_note(value: str) -> str:
    """Canonical single-line note text (the storefront ``normalize_line``
    contract, restated locally so hours imports no other domain): trim,
    collapse internal whitespace, Unicode NFC.
    """
    return unicodedata.normalize("NFC", " ".join(value.split()))


def has_control_characters(value: str) -> bool:
    """True when ``value`` carries a control character (category Cc).

    Rejected rather than stripped, for the storefront reason: a control
    character in a note is a paste accident or smuggling, and refusing the
    write keeps stored text exactly what the owner can see.
    """
    return any(unicodedata.category(char) == "Cc" for char in value)
