"""Public media delivery (M3D, ADR-017) — application composition.

Serving one image publicly needs two domains: **catalog** knows whether a
menu item currently shows the asset, **media** knows the asset inventory
and owns storage. Composing them here follows the M2D audit-list
precedent (authorization at the application layer, the domain stays pure)
and keeps the recorded dependency direction intact — media never imports
catalog.

Delivery requires every one of the approved conditions to be true *now*:
an active host-resolved Business, a same-Business asset, ``status =
'active'``, the requested representation present in the database
inventory, and at least one non-hidden menu item in a visible category
referencing it. Sold-out and non-orderable items still authorize their
image — those are ordering states, not visibility states. An asset that
is unknown, foreign, pending, expired, detached, or attached only through
hidden content is the **same** neutral 404, so no probe distinguishes
them.

``status = 'active'`` alone is deliberately not enough. Promotion is
one-way, so without the attachment check an asset detached (or hidden)
after promotion would remain publicly retrievable forever by anyone who
kept its URL.
"""

import uuid
from collections.abc import Iterator
from typing import Annotated, Any, BinaryIO

from fastapi import APIRouter, Depends, Path, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.database import get_session
from app.core.errors import ErrorEnvelope, ResourceNotFoundError
from app.domains.businesses.resolution import ResolvedBusiness, resolve_public_business
from app.domains.catalog import public_service as catalog_public
from app.domains.media import public_service as media_public
from app.domains.media.public_service import PublicRepresentation
from app.domains.media.storage import MediaStorage

public_media_router = APIRouter(prefix="/public", tags=["public"])

_MEDIA_TYPE = "image/webp"
_CHUNK_BYTES = 64 * 1024

_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_200_OK: {"content": {_MEDIA_TYPE: {}}},
    status.HTTP_304_NOT_MODIFIED: {"description": "Cached representation is current."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}

# The path parameters are plain strings, validated by hand, so a malformed
# identifier renders as the neutral public 404 instead of FastAPI's
# detailed 422 envelope (which would advertise the identifier's shape and
# break the uniform public contract). ``json_schema_extra`` keeps the
# documented contract honest — the generated client still sees a
# uuid-formatted string and the closed variant set — without turning a bad
# value into a validation error. No global validation behavior changes and
# administrative endpoints are untouched.
_AssetId = Annotated[str, Path(json_schema_extra={"format": "uuid"})]
_Variant = Annotated[str, Path(json_schema_extra={"enum": list(media_public.PUBLIC_VARIANTS)})]


def _representation_headers(representation: PublicRepresentation) -> dict[str, str]:
    """Headers describing the representation itself.

    ``Cache-Control`` is deliberately absent: ``NoStoreApiMiddleware`` is
    the single authority for cache policy on ``/api/v1`` and applies the
    public-media value to exactly the successful statuses, so no route can
    grant itself caching.
    """
    return {
        "Content-Length": str(representation.byte_size),
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "ETag": representation.etag,
    }


def _stream_and_close(stream: BinaryIO) -> Iterator[bytes]:
    """Yield the object in bounded chunks, always closing the handle.

    The ``finally`` runs on normal completion, on a streaming error, and on
    client disconnect (the generator is closed with ``GeneratorExit``), so
    a descriptor is never leaked and an ordinary disconnect is not mistaken
    for a storage fault. The route attaches a background close as well —
    ``close`` is idempotent, so the pair is safe (the M3C preview pattern).
    """
    try:
        while True:
            chunk = stream.read(_CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    finally:
        stream.close()


@public_media_router.head("/media/{asset_id}/{variant}", include_in_schema=False)
@public_media_router.get(
    "/media/{asset_id}/{variant}",
    operation_id="public_media_file_get",
    response_class=StreamingResponse,
    responses=_RESPONSES,
)
def public_media_file_get(
    asset_id: _AssetId,
    variant: _Variant,
    request: Request,
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
) -> Response:
    """Deliver one image of the Business resolved from the Host.

    Serves the re-encoded WebP canonical rendition or one of its
    responsive variants, addressed by opaque asset id and logical variant
    name. Supports conditional requests through a strong derived ETag;
    ``Range`` is ignored and the complete representation is returned.
    """
    storage: MediaStorage = request.app.state.media_storage
    business_id = business.business_id

    parsed_asset_id = media_public.parse_public_uuid(asset_id)
    if parsed_asset_id is None:
        raise ResourceNotFoundError()

    # Media: does this Business have an active asset with this
    # representation in the authoritative inventory?
    representation = media_public.find_public_representation(
        db, business_id=business_id, asset_id=parsed_asset_id, variant=variant
    )
    if representation is None:
        raise ResourceNotFoundError()

    # Catalog: is it currently on public display?
    if not catalog_public.media_is_publicly_visible(
        db, business_id=business_id, media_id=parsed_asset_id
    ):
        raise ResourceNotFoundError()

    # Eligibility is established from here on, so a storage problem is an
    # operational event worth recording (and only from here on).
    return _deliver(request, storage, business_id, representation)


def _deliver(
    request: Request,
    storage: MediaStorage,
    business_id: uuid.UUID,
    representation: PublicRepresentation,
) -> Response:
    """Validate the physical object, then answer 304, HEAD, or a stream."""
    stat = media_public.stat_object(storage, business_id=business_id, representation=representation)
    if stat is None:
        media_public.warn_object_anomaly(
            "media_object_missing",
            business_id=business_id,
            asset_id=representation.asset_id,
            variant=representation.variant,
        )
        raise ResourceNotFoundError()
    if stat.byte_size != representation.byte_size:
        # Storage and the database disagree about this object. Only size is
        # compared: routine delivery never hashes the object, so same-size
        # corruption is out of reach here by design and is detected by the
        # sweep's --verify and the backup preflight (docs/07) instead.
        media_public.warn_object_anomaly(
            "media_object_size_mismatch",
            business_id=business_id,
            asset_id=representation.asset_id,
            variant=representation.variant,
        )
        raise ResourceNotFoundError()

    headers = _representation_headers(representation)
    if media_public.if_none_match_matches(
        request.headers.get("if-none-match"), representation.etag
    ):
        # A matching validator still had to pass every check above: a 304
        # must never be issued for an object that is missing or whose size
        # contradicts the database. Only the read is skipped.
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": representation.etag},
        )

    if request.method == "HEAD":
        # Same representation headers as the GET, no body, and no open:
        # HEAD must never touch the object's contents.
        return Response(status_code=status.HTTP_200_OK, headers=headers, media_type=_MEDIA_TYPE)

    # Open before committing any response header, so an object that
    # disappears between stat and open is still a clean neutral 404 rather
    # than a 200 whose body stops short of its Content-Length.
    stream = media_public.open_object(
        storage, business_id=business_id, representation=representation
    )
    if stream is None:
        media_public.warn_object_anomaly(
            "media_object_unreadable",
            business_id=business_id,
            asset_id=representation.asset_id,
            variant=representation.variant,
        )
        raise ResourceNotFoundError()

    return StreamingResponse(
        _stream_and_close(stream),
        media_type=_MEDIA_TYPE,
        headers=headers,
        background=BackgroundTask(stream.close),
    )
