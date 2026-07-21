"""Media policy constants and filename sanitization (M3C, ADR-017)."""

import unicodedata

from app.domains.media import policies


def test_ruled_limit_constants_are_exact() -> None:
    """The final-correction values are pinned; changing one is a ruling."""
    assert policies.MAX_MEDIA_ASSETS_PER_BUSINESS == 500
    assert policies.MAX_MEDIA_BYTES_PER_BUSINESS == 1_073_741_824
    assert policies.MAX_ASSET_OUTPUT_BYTES == 33_554_432
    assert policies.DEFAULT_UPLOAD_MAX_BYTES == 10 * 1024 * 1024
    assert policies.MAX_UPLOAD_MAX_BYTES == 20 * 1024 * 1024
    assert policies.MULTIPART_OVERHEAD_BYTES == 65_536
    assert policies.MAX_SOURCE_DIMENSION == 8_000
    assert policies.MAX_SOURCE_PIXELS == 25_000_000
    assert policies.CANONICAL_MAX_DIMENSION == 2_560
    assert policies.VARIANT_WIDTHS == (320, 640, 1280)
    assert policies.VARIANT_NAMES == ("w320", "w640", "w1280")
    assert policies.PENDING_TTL_HOURS == 48
    assert policies.ORPHAN_SAFETY_AGE_HOURS == 24
    assert policies.MAX_ORIGINAL_FILENAME_LENGTH == 160
    assert policies.MAX_IMAGE_ALT_LENGTH == 300
    assert policies.MEDIA_LIST_PAGE_LIMIT == 100


class TestSanitizeFilename:
    def test_strips_path_components_of_both_separator_styles(self) -> None:
        # Both separator styles collapse to the final path segment.
        assert policies.sanitize_filename("C:\\Users\\evil\\photo.jpg") == "photo.jpg"
        assert policies.sanitize_filename("/etc/passwd") == "passwd"
        assert policies.sanitize_filename("a/b/c/dish.webp") == "dish.webp"
        # A trailing traversal segment survives only as inert display text
        # (it never touches a storage path).
        assert policies.sanitize_filename("x/..") == ".."

    def test_removes_control_characters(self) -> None:
        assert policies.sanitize_filename("dish\x00\x1f\x7f.jpg") == "dish.jpg"

    def test_normalizes_to_nfc_and_trims(self) -> None:
        # NFD input ('e' + combining acute) must come out composed (NFC).
        composed = "café.png"
        decomposed = unicodedata.normalize("NFD", composed)
        assert decomposed != composed  # the fixture is genuinely decomposed
        assert policies.sanitize_filename(f"  {decomposed}  ") == composed

    def test_empty_input_falls_back_to_neutral_name(self) -> None:
        assert policies.sanitize_filename("") == "upload"
        assert policies.sanitize_filename("   ") == "upload"
        assert policies.sanitize_filename("dir/") == "upload"

    def test_bounded_to_160_characters(self) -> None:
        assert len(policies.sanitize_filename("x" * 500)) == 160
