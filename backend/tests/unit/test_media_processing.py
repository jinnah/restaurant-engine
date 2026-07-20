"""Secure, deterministic image processing (M3C, ADR-017 R3/R4).

Fixtures are built in-memory with Pillow; nothing touches storage, the
database, or the development media root.
"""

import io
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from app.domains.media import processing
from app.domains.media.processing import ImageValidationError, process_image


def _encode(image: Image.Image, fmt: str, **params: object) -> io.BytesIO:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **params)
    buffer.seek(0)
    return buffer


def _jpeg(width: int, height: int, color: tuple[int, int, int] = (200, 80, 40)) -> io.BytesIO:
    return _encode(Image.new("RGB", (width, height), color), "JPEG")


def _png_rgba(width: int, height: int) -> io.BytesIO:
    return _encode(Image.new("RGBA", (width, height), (10, 20, 30, 128)), "PNG")


class TestAcceptedFormats:
    def test_jpeg_is_processed_to_webp(self, tmp_path: Path) -> None:
        result = process_image(_jpeg(800, 600), tmp_path)
        assert result.source_format == "jpeg"
        assert result.canonical.variant == "canonical"
        assert result.canonical.width == 800
        # Output is always WebP and the file exists.
        assert result.canonical.path.read_bytes()[:4] == b"RIFF"

    def test_png_is_processed_and_alpha_preserved(self, tmp_path: Path) -> None:
        result = process_image(_png_rgba(400, 400), tmp_path)
        assert result.source_format == "png"
        reopened = Image.open(result.canonical.path)
        assert reopened.mode == "RGBA"  # alpha survived the re-encode

    def test_webp_source_is_accepted(self, tmp_path: Path) -> None:
        source = _encode(Image.new("RGB", (300, 300), (0, 0, 0)), "WEBP")
        result = process_image(source, tmp_path)
        assert result.source_format == "webp"


class TestVariantGeneration:
    def test_variants_only_below_canonical_width(self, tmp_path: Path) -> None:
        # 1000px wide canonical -> only 320 and 640 variants (1280 >= 1000).
        result = process_image(_jpeg(1000, 500), tmp_path)
        widths = {v.variant for v in result.variants}
        assert widths == {"w320", "w640"}
        assert all(v.width < result.canonical.width for v in result.variants)

    def test_tiny_image_gets_no_variants(self, tmp_path: Path) -> None:
        result = process_image(_jpeg(200, 200), tmp_path)
        assert result.variants == ()

    def test_canonical_downscaled_to_2560_longest_side(self, tmp_path: Path) -> None:
        result = process_image(_jpeg(4000, 2000), tmp_path)
        assert result.canonical.width == 2560
        # Deterministic rounding: 2000 * 2560 / 4000 = 1280.
        assert result.canonical.height == 1280

    def test_no_upscaling(self, tmp_path: Path) -> None:
        result = process_image(_jpeg(500, 500), tmp_path)
        assert result.canonical.width == 500  # unchanged, never enlarged

    def test_portrait_downscale_uses_height_as_longest(self, tmp_path: Path) -> None:
        result = process_image(_jpeg(2000, 4000), tmp_path)
        assert result.canonical.height == 2560
        assert result.canonical.width == 1280

    def test_processing_is_deterministic(self, tmp_path: Path) -> None:
        first = process_image(_jpeg(1200, 900), tmp_path)
        second = process_image(_jpeg(1200, 900), tmp_path)
        assert first.canonical.checksum_sha256 == second.canonical.checksum_sha256
        assert [v.checksum_sha256 for v in first.variants] == [
            v.checksum_sha256 for v in second.variants
        ]


class TestRejections:
    def test_non_image_bytes_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ImageValidationError, match="unsupported file type"):
            process_image(io.BytesIO(b"this is not an image"), tmp_path)

    def test_signature_content_mismatch_rejected(self, tmp_path: Path) -> None:
        # PNG magic bytes prepended to JPEG content: sniff says png, decoded
        # format says jpeg -> rejected.
        jpeg = _jpeg(100, 100).read()
        spoofed = io.BytesIO(b"\x89PNG\r\n\x1a\n" + jpeg)
        with pytest.raises(ImageValidationError):
            process_image(spoofed, tmp_path)

    def test_oversized_dimension_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ImageValidationError, match="dimensions exceed"):
            process_image(_jpeg(8001, 10), tmp_path)

    def test_too_many_pixels_rejected(self, tmp_path: Path) -> None:
        # 6000 x 5000 = 30 MP > 25 MP but each side < 8000.
        with pytest.raises(ImageValidationError, match="too many pixels"):
            process_image(_jpeg(6000, 5000), tmp_path)

    def test_animated_webp_rejected(self, tmp_path: Path) -> None:
        frames = [Image.new("RGB", (64, 64), (i * 40, 0, 0)) for i in range(3)]
        buffer = io.BytesIO()
        frames[0].save(buffer, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
        buffer.seek(0)
        with pytest.raises(ImageValidationError, match="animated"):
            process_image(buffer, tmp_path)

    def test_apng_rejected(self, tmp_path: Path) -> None:
        frames = [Image.new("RGBA", (64, 64), (i * 40, 0, 0, 255)) for i in range(3)]
        buffer = io.BytesIO()
        frames[0].save(buffer, format="PNG", save_all=True, append_images=frames[1:], duration=100)
        buffer.seek(0)
        with pytest.raises(ImageValidationError, match="animated"):
            process_image(buffer, tmp_path)

    def test_truncated_image_rejected(self, tmp_path: Path) -> None:
        full = _jpeg(400, 400).read()
        truncated = io.BytesIO(full[: len(full) // 2])
        with pytest.raises(ImageValidationError):
            process_image(truncated, tmp_path)

    def test_output_over_32_mib_is_a_processing_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the output bound low so a normal image trips it; proves the
        # 32 MiB ceiling is a processing (422-shaped) failure, not a quota.
        monkeypatch.setattr(processing, "MAX_ASSET_OUTPUT_BYTES", 10)
        with pytest.raises(ImageValidationError, match="per-asset size bound"):
            process_image(_jpeg(1200, 900), tmp_path)
        # No encoded files are left behind on rejection.
        assert list(tmp_path.iterdir()) == []


class TestMetadataStripping:
    def test_exif_orientation_applied_and_metadata_removed(self, tmp_path: Path) -> None:
        # A landscape image tagged orientation=6 (rotate 90) must come out
        # physically rotated to portrait, with no EXIF in the output.
        base = Image.new("RGB", (200, 100), (123, 50, 200))
        exif = base.getexif()
        exif[274] = 6  # Orientation tag
        buffer = io.BytesIO()
        base.save(buffer, format="JPEG", exif=exif)
        buffer.seek(0)
        result = process_image(buffer, tmp_path)
        reopened = Image.open(result.canonical.path)
        assert reopened.width == 100  # transposed from 200x100
        assert reopened.height == 200
        assert not reopened.getexif()  # metadata stripped

    def test_png_text_metadata_removed(self, tmp_path: Path) -> None:
        image = Image.new("RGB", (120, 120), (1, 2, 3))
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Comment", "secret gps data")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", pnginfo=meta)
        buffer.seek(0)
        result = process_image(buffer, tmp_path)
        reopened = Image.open(result.canonical.path)
        assert "Comment" not in (reopened.info or {})
