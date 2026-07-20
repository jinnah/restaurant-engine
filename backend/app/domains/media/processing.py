"""Secure, deterministic image processing (M3C, ADR-017 R3/R4).

The pipeline (final correction 8):

1. magic-byte sniff (static JPEG/PNG/WebP signatures);
2. ``Image.open`` — the decoded ``format`` is authoritative and must
   agree with the sniff;
3. header-stage bounds before full decode: 8,000 px/side, 25 MP, and
   frame-count/animation inspection (animated WebP and APNG rejected);
4. ``verify()`` structural validation, then reopen (Pillow contract)
   and fully decode — truncated images reject
   (``ImageFile.LOAD_TRUNCATED_IMAGES`` stays disabled);
5. EXIF orientation applied; deterministic mode normalization
   (transparency → RGBA, everything else → RGB, sRGB assumed — ICC
   profiles are metadata and are dropped with the rest);
6. longest side downscaled to at most 2,560 px (LANCZOS, banker's
   rounding via ``round``, never upscaled); variants only where the
   target width is strictly smaller than the canonical width;
7. WebP encode with fixed parameters — quality 82, method 4, lossy,
   alpha preserved — passing no EXIF/ICC/XMP, so every non-pixel byte
   is absent from output by construction. The original upload is not
   retained.

Decompression-bomb policy (configured once at import — no per-request
warnings-filter mutation, so behavior is deterministic under
concurrency): ``Image.MAX_IMAGE_PIXELS`` is set to half the policy
bound, which makes Pillow raise ``DecompressionBombError`` above the
bound (Pillow errors at 2x its setting) as defense in depth behind our
explicit header check; the accompanying warning band (12.5-25 MP) is
legitimate input and is silenced.

No antivirus protection exists and none is claimed; full re-encoding is
the sanitization mechanism.
"""

import hashlib
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps

from app.domains.media.policies import (
    CANONICAL_MAX_DIMENSION,
    CANONICAL_VARIANT,
    MAX_ASSET_OUTPUT_BYTES,
    MAX_SOURCE_DIMENSION,
    MAX_SOURCE_PIXELS,
    VARIANT_WIDTHS,
)

# Deterministic WebP parameters (final correction 8): fixed so output
# bytes, CPU cost, and checksum-based tests are reproducible for the
# pinned Pillow version.
WEBP_QUALITY = 82
WEBP_METHOD = 4

# Import-time bomb configuration (see module docstring).
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS // 2
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

_PILLOW_FORMATS = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}


class ImageValidationError(Exception):
    """The upload is not an acceptable static image (client-safe text)."""


def detect_signature(header: bytes) -> str | None:
    """Detect the source format from magic bytes (allowlist only)."""
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(header) >= 12 and header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


@dataclass(frozen=True)
class EncodedObject:
    """One encoded output file (canonical or a variant) in the work dir."""

    variant: str  # 'canonical' or 'w320'/'w640'/'w1280'
    path: Path
    width: int
    height: int
    byte_size: int
    checksum_sha256: str


@dataclass(frozen=True)
class ProcessedImage:
    """The complete deterministic processing result."""

    source_format: str  # 'jpeg' | 'png' | 'webp'
    canonical: EncodedObject
    variants: tuple[EncodedObject, ...]  # strictly-smaller widths only

    @property
    def total_bytes(self) -> int:
        return self.canonical.byte_size + sum(item.byte_size for item in self.variants)


def _scaled(width: int, height: int, target_width: int) -> tuple[int, int]:
    """Deterministic target dimensions (``round`` = banker's rounding)."""
    scaled_height = max(1, round(height * target_width / width))
    return target_width, scaled_height


def _normalized_mode(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        return image
    has_alpha = image.mode in ("LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    return image.convert("RGBA" if has_alpha else "RGB")


def _encode(image: Image.Image, variant: str, work_dir: Path) -> EncodedObject:
    path = work_dir / f"encode-{variant}-{uuid.uuid4()}.webp"
    with path.open("wb") as handle:
        image.save(handle, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD, lossless=False)
    data = path.read_bytes()
    return EncodedObject(
        variant=variant,
        path=path,
        width=image.width,
        height=image.height,
        byte_size=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )


def process_image(source: BinaryIO, work_dir: Path) -> ProcessedImage:
    """Validate and re-encode one upload; raises ``ImageValidationError``.

    ``work_dir`` receives the encoded temp files; the caller owns their
    lifecycle (upload flow: stream to storage, then always delete).
    """
    source.seek(0)
    sniffed = detect_signature(source.read(16))
    if sniffed is None:
        msg = "unsupported file type; upload a static JPEG, PNG, or WebP image"
        raise ImageValidationError(msg)

    source.seek(0)
    try:
        probe = Image.open(source)
    except Image.DecompressionBombError as exc:
        msg = "image has too many pixels"
        raise ImageValidationError(msg) from exc
    except OSError as exc:
        msg = "file is not a valid image"
        raise ImageValidationError(msg) from exc

    if probe.format != _PILLOW_FORMATS[sniffed]:
        msg = "file content does not match its image signature"
        raise ImageValidationError(msg)
    width, height = probe.size
    if width > MAX_SOURCE_DIMENSION or height > MAX_SOURCE_DIMENSION:
        msg = f"image dimensions exceed {MAX_SOURCE_DIMENSION} pixels per side"
        raise ImageValidationError(msg)
    if width * height > MAX_SOURCE_PIXELS:
        msg = "image has too many pixels"
        raise ImageValidationError(msg)
    if getattr(probe, "is_animated", False) or getattr(probe, "n_frames", 1) > 1:
        msg = "animated images are not supported"
        raise ImageValidationError(msg)
    try:
        probe.verify()
    except Exception as exc:
        msg = "image failed structural validation"
        raise ImageValidationError(msg) from exc

    # Pillow contract: a verified image must be reopened before use.
    source.seek(0)
    try:
        image = Image.open(source)
        image.load()  # full decode; truncated data raises here
    except Image.DecompressionBombError as exc:
        msg = "image has too many pixels"
        raise ImageValidationError(msg) from exc
    except OSError as exc:
        msg = "image data is corrupt or truncated"
        raise ImageValidationError(msg) from exc

    # exif_transpose returns None only when passed None; our input is a
    # decoded image, so the result is always an image.
    transposed = ImageOps.exif_transpose(image)
    assert transposed is not None  # noqa: S101 - narrows the Optional return
    normalized: Image.Image = _normalized_mode(transposed)

    longest = max(normalized.width, normalized.height)
    if longest > CANONICAL_MAX_DIMENSION:
        if normalized.width >= normalized.height:
            target = _scaled(normalized.width, normalized.height, CANONICAL_MAX_DIMENSION)
        else:
            scaled_width = max(
                1, round(normalized.width * CANONICAL_MAX_DIMENSION / normalized.height)
            )
            target = (scaled_width, CANONICAL_MAX_DIMENSION)
        normalized = normalized.resize(target, Image.Resampling.LANCZOS)

    encoded: list[EncodedObject] = []
    try:
        canonical = _encode(normalized, CANONICAL_VARIANT, work_dir)
        encoded.append(canonical)
        variants: list[EncodedObject] = []
        for target_width in VARIANT_WIDTHS:
            if target_width >= canonical.width:
                continue  # never upscale; strictly-smaller widths only
            resized = normalized.resize(
                _scaled(canonical.width, canonical.height, target_width),
                Image.Resampling.LANCZOS,
            )
            variant = _encode(resized, f"w{target_width}", work_dir)
            encoded.append(variant)
            variants.append(variant)
    except ImageValidationError:
        for item in encoded:
            item.path.unlink(missing_ok=True)
        raise
    except OSError:
        for item in encoded:
            item.path.unlink(missing_ok=True)
        raise

    result = ProcessedImage(
        source_format=sniffed,
        canonical=canonical,
        variants=tuple(variants),
    )
    if result.total_bytes > MAX_ASSET_OUTPUT_BYTES:
        for item in encoded:
            item.path.unlink(missing_ok=True)
        msg = "encoded image output exceeds the per-asset size bound"
        raise ImageValidationError(msg)
    return result
