"""Media API schemas (M3C, ADR-017).

Responses are explicit projections — never serialized ORM objects, and
never carrying a storage key, filesystem path, checksum, or any internal
storage metadata (ruling R3/R4). ``pending_expires_at`` is surfaced so an
administrator can see when a pending asset expires; it is null for active
assets (the explicit-nullable response convention, unlike the audit-only
omit-None rule).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MediaVariantView(BaseModel):
    """One generated responsive rendition (no key, no checksum)."""

    variant: Literal["w320", "w640", "w1280"]
    width: int
    height: int
    byte_size: int


class MediaAssetView(BaseModel):
    """One media asset (administrative projection).

    Deliberately excludes ``checksum_sha256`` and every storage key/path:
    those are internal storage metadata (R3/R4). ``pending_expires_at`` is
    populated only for pending assets.
    """

    id: uuid.UUID
    kind: Literal["image"]
    status: Literal["pending", "active"]
    pending_expires_at: datetime | None
    original_filename: str
    source_format: Literal["jpeg", "png", "webp"]
    width: int
    height: int
    byte_size: int
    variants: list[MediaVariantView]
    created_at: datetime
    updated_at: datetime


class MediaAssetPage(BaseModel):
    """One page of a business's media assets (limit/offset, newest first)."""

    items: list[MediaAssetView]
    total: int
    limit: int
    offset: int


class MediaDeletedResponse(BaseModel):
    """Explicit confirmation body for the media delete command."""

    status: Literal["deleted"] = "deleted"
