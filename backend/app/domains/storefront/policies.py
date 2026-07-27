"""Storefront composition policy constants and text normalization (M4A).

Centralized code policy, like ``catalog.policies``: uniform across tenants,
not deployment-tunable, and not tenant-configurable. Bounds keep a stored
configuration, its audit projections, and every future rendered page
bounded; they are enforced by the schemas (422) and, where a CHECK can
express them, by the database.

All storefront copy is **plain text**. There is no rich-text, Markdown, or
HTML field anywhere in the registry, and none may be added without an
architecture decision (blueprint §12.3: no tenant CSS, JavaScript, or
arbitrary HTML).
"""

import unicodedata

# --- Structure bounds --------------------------------------------------------
# The section-count bound is derived from the registry itself
# (``composition.MAX_SECTIONS``): at most one section per registered type,
# which is the standing guard against a general-purpose page builder.
MAX_SECTION_ID_LENGTH = 64
# Structural key, not display text: a stable slug the owner never sees as
# copy. Deliberately ASCII — it identifies a section across reorders and
# must round-trip through URLs, logs, and test fixtures unchanged.
SECTION_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$"

# --- Text bounds -------------------------------------------------------------
MAX_HEADING_LENGTH = 120
MAX_SUBHEADING_LENGTH = 300
MAX_INTRO_LENGTH = 500
MAX_BODY_LENGTH = 4000
MAX_ADDRESS_LINES = 4
MAX_ADDRESS_LINE_LENGTH = 120
MAX_PHONE_LENGTH = 40
MAX_EMAIL_LENGTH = 254

# --- Media bounds ------------------------------------------------------------
MAX_GALLERY_IMAGES = 12
# Contextual alt text of one storefront image attachment. Mirrors
# ``catalog.policies.MAX_IMAGE_ALT_LENGTH`` and
# ``media.policies.MAX_IMAGE_ALT_LENGTH``; a pinned test keeps all three
# equal, so one contract cannot drift from the others.
MAX_IMAGE_ALT_LENGTH = 300

# --- Theme -------------------------------------------------------------------
# A curated accent token, not a stylesheet: exactly a six-digit hex colour
# (blueprint §12.3 permits accent tokens and forbids tenant CSS).
ACCENT_PATTERN = r"^#[0-9a-f]{6}$"
DEFAULT_ACCENT = "#a34b2a"


def normalize_line(value: str) -> str:
    """Canonical single-line display text.

    Trim, collapse every internal whitespace run to one space, then Unicode
    NFC — the ``catalog.policies.normalize_name`` contract, applied to all
    storefront copy so equality, length bounds, and stored bytes are
    canonical for every script. NFC matters for the launch market: Bengali
    combining sequences have multiple encodings of the same text, and only
    a normalized form compares and measures consistently.
    """
    return unicodedata.normalize("NFC", " ".join(value.split()))


def normalize_block(value: str) -> str:
    """Canonical multi-line display text (paragraphs preserved).

    Like :func:`normalize_line` but newlines survive: each line is
    individually collapsed and trimmed, blank lines are kept as paragraph
    breaks, and leading/trailing blank lines are dropped. Line endings are
    normalized to ``\\n`` so a CRLF paste and a LF paste store identically.
    """
    lines = [" ".join(line.split()) for line in value.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return unicodedata.normalize("NFC", "\n".join(lines))


def has_control_characters(value: str, *, allow_newline: bool = False) -> bool:
    """True when ``value`` carries a disallowed control character.

    Rejected rather than stripped: a control character in restaurant copy is
    always either a paste accident or an attempt to smuggle something past a
    later consumer (logs, CSV exports, terminal output). Refusing the write
    keeps the stored text exactly what the owner can see in the editor.
    ``category(ch) == "Cc"`` covers C0/C1; the newline exemption exists only
    for block text.
    """
    for char in value:
        if char == "\n" and allow_newline:
            continue
        if unicodedata.category(char) == "Cc":
            return True
    return False
