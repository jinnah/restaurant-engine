"""Media product-policy constants and filename sanitization (M3C, ADR-017).

Centralized code policy: uniform across tenants and not tenant-
configurable. The single deliberate exception is the upload byte cap,
which is a bounded deployment setting (``MEDIA_UPLOAD_MAX_BYTES``,
default/maximum below) per ruling R2. Count- and byte-quota enforcement
runs in the service under the Business row lock from authoritative rows
— there is deliberately no stored byte total to drift (final
correction 1).
"""

import unicodedata

# --- Quotas (final correction 5 / approved decision 16) ----------------------
# Pending and active assets both count; canonical and every variant byte
# counts toward stored usage.
MAX_MEDIA_ASSETS_PER_BUSINESS = 500
MAX_MEDIA_BYTES_PER_BUSINESS = 1_073_741_824  # 1 GiB
# Combined canonical-plus-variant encoded output for ONE asset. Exceeding
# it is an image-processing validation failure (422), never a quota 409.
MAX_ASSET_OUTPUT_BYTES = 33_554_432  # 32 MiB

# --- Upload caps (R2; the byte cap is the one deployment setting) ------------
DEFAULT_UPLOAD_MAX_BYTES = 10_485_760  # 10 MiB
MAX_UPLOAD_MAX_BYTES = 20_971_520  # 20 MiB
# Fixed allowance for the multipart envelope (boundaries + part headers)
# on top of the file cap; the raw request stream and the extracted file
# are bounded independently (final correction on upload-cap semantics).
MULTIPART_OVERHEAD_BYTES = 65_536  # 64 KiB

# --- Source-image bounds (R2) ------------------------------------------------
MAX_SOURCE_DIMENSION = 8_000  # px per side
MAX_SOURCE_PIXELS = 25_000_000  # 25 megapixels

# --- Canonical encoding (R3/R4) ----------------------------------------------
CANONICAL_MAX_DIMENSION = 2_560
VARIANT_WIDTHS = (320, 640, 1280)
CANONICAL_VARIANT = "canonical"
VARIANT_NAMES = tuple(f"w{width}" for width in VARIANT_WIDTHS)

# --- Lifecycle (R7) -----------------------------------------------------------
PENDING_TTL_HOURS = 48
# Storage-only objects younger than this are never sweep-deleted (they may
# belong to an in-flight upload whose row has not committed yet); the age
# is judged from storage last-modified metadata, never filename guesses.
ORPHAN_SAFETY_AGE_HOURS = 24

# --- Text bounds (R2) ---------------------------------------------------------
MAX_ORIGINAL_FILENAME_LENGTH = 160
MAX_IMAGE_ALT_LENGTH = 300

# --- List pagination (R2) -----------------------------------------------------
MEDIA_LIST_PAGE_LIMIT = 100


def sanitize_filename(raw: str) -> str:
    """Display-safe form of a client-supplied filename (metadata only).

    Storage keys never contain this value. Path components are stripped
    (last segment wins across both separator styles), control characters
    removed, Unicode normalized to NFC, whitespace trimmed, and the
    result bounded to ``MAX_ORIGINAL_FILENAME_LENGTH``; an empty result
    falls back to a fixed neutral name so the NOT NULL + length CHECKs
    always hold.
    """
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ord(ch) >= 32 and ch != "\x7f")
    name = unicodedata.normalize("NFC", name).strip()
    if not name:
        name = "upload"
    return name[:MAX_ORIGINAL_FILENAME_LENGTH]
