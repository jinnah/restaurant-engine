"""Public media delivery: inventory, validators, and object access (M3D).

The media half of the public delivery surface. It answers three questions
and nothing else:

* does this Business have an **active** asset with this id, and does the
  requested representation exist in the authoritative database inventory?
* what are that representation's byte size and opaque validator?
* can its stored object be stat-ed and opened?

It deliberately knows nothing about *why* an asset may be shown. Whether a
menu item currently displays it is a catalog question, and this module must
not import catalog — the recorded dependency direction is catalog → media
(ADR-017 M3C final correction M). The application-layer router
(``app/api/public_media_router.py``) joins the two halves.

Internal storage keys, paths, and stored checksums never leave this module:
callers receive a ``PublicRepresentation`` carrying a derived, opaque ETag
and a byte size, never the key or the checksum itself.
"""

import hashlib
import uuid
from dataclasses import dataclass
from typing import BinaryIO, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.media import policies
from app.domains.media.models import MediaAsset, MediaAssetVariant
from app.domains.media.storage import (
    MediaStorage,
    ObjectNotFoundError,
    StoredObjectStat,
    object_key,
)

_LOGGER_NAME = "app.media.public"

# The logical representations a public request may name. Mirrors the
# database CHECK on media_asset_variants plus the canonical rendition.
PUBLIC_VARIANTS: tuple[str, ...] = (policies.CANONICAL_VARIANT, *policies.VARIANT_NAMES)

# Versioned ETag input prefix. Bumping it invalidates every previously
# issued validator without touching stored bytes — the reason the tuple is
# versioned at all.
_ETAG_VERSION = "rem1"

ObjectAnomaly = Literal[
    "media_object_missing", "media_object_size_mismatch", "media_object_unreadable"
]


@dataclass(frozen=True)
class PublicRepresentation:
    """One deliverable rendition, as the database describes it.

    ``etag`` is derived from the checksum of *this* representation (the
    asset row for ``canonical``, the variant row otherwise), so two
    renditions of one asset never share a validator. The stored checksum
    itself is never exposed (ADR-017 R3).
    """

    asset_id: uuid.UUID
    variant: str
    byte_size: int
    etag: str


def _derive_etag(asset_id: uuid.UUID, variant: str, checksum: str) -> str:
    """A strong, opaque validator for one representation.

    Strong because the bytes at (asset id, variant) are immutable: asset
    identity never changes in place, replacement is a new asset. Derived
    rather than the raw checksum so no stored checksum is ever returned;
    the full digest is returned, never truncated.
    """
    material = f"{_ETAG_VERSION}|{asset_id}|{variant}|{checksum}".encode()
    return f'"{hashlib.sha256(material).hexdigest()}"'


def parse_public_uuid(raw: str) -> uuid.UUID | None:
    """A canonical hyphenated UUID, case-insensitively; else ``None``.

    The public contract is the canonical 8-4-4-4-12 hyphenated form.
    Braced, ``urn:uuid:``, and hyphenless spellings are rejected rather
    than silently normalized: accepting them would mint alias URLs for one
    resource, fragmenting caches and multiplying the surface an operator
    has to reason about. Uppercase input is accepted and normalized, so
    ``ABCD…`` and ``abcd…`` address exactly the same object.

    Returning ``None`` (rather than raising a validation error) is what
    lets the caller answer with the neutral public 404 instead of a
    detailed 422 envelope that would advertise the identifier's shape.
    """
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return None
    if raw.lower() != str(parsed):
        return None
    return parsed


def if_none_match_matches(header: str | None, etag: str) -> bool:
    """RFC 9110 ``If-None-Match`` evaluation for GET/HEAD.

    Supports ``*``, comma-separated validator lists, and weak comparison
    (a ``W/`` prefix is ignored, which is the required comparison function
    for GET and HEAD). Anything unparseable simply fails to match, so the
    request falls through to a normal 200 rather than erroring.
    """
    if not header:
        return False
    candidates = [candidate.strip() for candidate in header.split(",")]
    if "*" in candidates:
        return True
    for candidate in candidates:
        value = candidate[2:] if candidate[:2].upper() == "W/" else candidate
        if value == etag:
            return True
    return False


def find_public_representation(
    db: Session, *, business_id: uuid.UUID, asset_id: uuid.UUID, variant: str
) -> PublicRepresentation | None:
    """The requested representation of an **active** asset of this Business.

    ``None`` for an unknown, foreign, pending, or expired-pending asset, a
    non-image asset, an unknown variant name, or a derived variant with no
    inventory row. Every one of those becomes the same neutral 404, so the
    caller never has to distinguish them.

    Pending assets are excluded here, not filtered later: public delivery
    never serves pending media (ADR-017 R7), and an expired-pending asset
    is still ``status = 'pending'``, so the single predicate covers both.
    """
    if variant not in PUBLIC_VARIANTS:
        return None
    asset = db.execute(
        select(MediaAsset).where(
            MediaAsset.business_id == business_id,
            MediaAsset.id == asset_id,
            MediaAsset.status == "active",
            MediaAsset.kind == "image",
        )
    ).scalar_one_or_none()
    if asset is None:
        return None

    if variant == policies.CANONICAL_VARIANT:
        return PublicRepresentation(
            asset_id=asset_id,
            variant=variant,
            byte_size=asset.byte_size,
            etag=_derive_etag(asset_id, variant, asset.checksum_sha256),
        )

    row = db.execute(
        select(MediaAssetVariant).where(
            MediaAssetVariant.business_id == business_id,
            MediaAssetVariant.asset_id == asset_id,
            MediaAssetVariant.variant == variant,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return PublicRepresentation(
        asset_id=asset_id,
        variant=variant,
        byte_size=row.byte_size,
        etag=_derive_etag(asset_id, variant, row.checksum_sha256),
    )


def list_public_representations(
    db: Session, *, business_id: uuid.UUID, asset_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, MediaAsset], dict[uuid.UUID, list[MediaAssetVariant]]]:
    """Active assets and their variants for a bounded set of ids.

    Used by the public menu projection to describe images. Only active
    assets are returned, so an item whose asset is pending or gone simply
    projects without an image rather than advertising a URL that would
    404. Variants come back width-ascending — the order a responsive
    ``srcset`` needs — deliberately not the administrative byte-size
    order, which is not guaranteed to be monotonic in width.
    """
    if not asset_ids:
        return {}, {}
    assets = {
        asset.id: asset
        for asset in db.execute(
            select(MediaAsset).where(
                MediaAsset.business_id == business_id,
                MediaAsset.id.in_(asset_ids),
                MediaAsset.status == "active",
                MediaAsset.kind == "image",
            )
        ).scalars()
    }
    if not assets:
        return {}, {}
    variants: dict[uuid.UUID, list[MediaAssetVariant]] = {}
    rows = db.execute(
        select(MediaAssetVariant)
        .where(
            MediaAssetVariant.business_id == business_id,
            MediaAssetVariant.asset_id.in_(list(assets)),
        )
        .order_by(MediaAssetVariant.asset_id, MediaAssetVariant.width, MediaAssetVariant.variant)
    ).scalars()
    for row in rows:
        variants.setdefault(row.asset_id, []).append(row)
    return assets, variants


def stat_object(
    storage: MediaStorage, *, business_id: uuid.UUID, representation: PublicRepresentation
) -> StoredObjectStat | None:
    """Storage metadata for a representation, or ``None`` if unavailable.

    Failure-safe like the sweep's verification: a missing object and an
    unreadable one both yield ``None`` rather than raising, so a storage
    fault can never surface as a 500 on an unauthenticated route.
    """
    try:
        return storage.stat(
            key=object_key(business_id, representation.asset_id, representation.variant)
        )
    except (ObjectNotFoundError, ValueError, OSError):
        return None


def open_object(
    storage: MediaStorage, *, business_id: uuid.UUID, representation: PublicRepresentation
) -> BinaryIO | None:
    """Open the stored object, or ``None`` if it cannot be opened.

    Called only after ``stat_object`` succeeded, so ``None`` here means the
    object disappeared or became unreadable in between. Returning ``None``
    instead of raising keeps that race on the neutral-404 path, before any
    response header is committed — never a truncated 200.
    """
    try:
        return storage.open(
            key=object_key(business_id, representation.asset_id, representation.variant)
        )
    except (ObjectNotFoundError, ValueError, OSError):
        return None


def warn_object_anomaly(
    reason: ObjectAnomaly, *, business_id: uuid.UUID, asset_id: uuid.UUID, variant: str
) -> None:
    """Record a storage anomaly for an asset that *should* be deliverable.

    Only ever called after the database has established that the asset is
    currently eligible for public delivery, so an ordinary public miss —
    unknown, foreign, pending, detached, hidden-only, malformed id,
    unknown variant — never reaches here. That restraint is deliberate:
    logging expected misses would hand an unauthenticated caller a
    log-amplification vector.

    The payload is exactly the approved identifiers plus a reason code;
    never a Host, storage key, path, filename, checksum, or exception
    message (ADR-017 R3). Static context (service, environment, request
    id) is added by the shared logging processors.

    The logger is resolved per call rather than cached at import: logging
    is configured with ``cache_logger_on_first_use``, so a module-level
    proxy would freeze whichever configuration happened to be active at
    its first use. This path fires only on a genuine storage anomaly, so
    the lookup cost is irrelevant next to always honoring the current
    configuration.
    """
    structlog.get_logger(_LOGGER_NAME).warning(
        reason,
        business_id=str(business_id),
        asset_id=str(asset_id),
        variant=variant,
    )
