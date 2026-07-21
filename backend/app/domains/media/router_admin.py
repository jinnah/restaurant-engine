"""Business-scoped media administration endpoints (M3C, ADR-017).

Routers translate only (docs/02): the service enforces capabilities, the
Business row lock, quotas, and lifecycle. The tenant comes from the route
path and is validated against the caller's membership inside the service
(nonmembers, including platform admins, get 404). Every unsafe route
carries the two M2A CSRF layers. Operation IDs are permanent client
contracts (ADR-009).

The upload route declares **no body parameters** so FastAPI never parses
the multipart body before dependencies run (the binding upload
correction); its request body is documented manually via ``openapi_extra``.
Processing and the authoritative transaction run in an AnyIO worker
thread so Pillow and blocking I/O never touch the event loop, and no
SQLAlchemy session crosses the thread boundary (final correction 2).
"""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, BinaryIO

import anyio
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.background import BackgroundTask

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.core.settings import Settings
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor
from app.domains.media import policies, service
from app.domains.media.policies import CANONICAL_VARIANT
from app.domains.media.schemas import MediaAssetPage, MediaAssetView, MediaDeletedResponse
from app.domains.media.service_support import authorize_write_nonlocking
from app.domains.media.storage import MediaStorage
from app.domains.media.upload import read_bounded_body

media_admin_router = APIRouter(prefix="/businesses/{business_id}/media", tags=["media"])

_READ_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}
_WRITE_ENVELOPES: dict[int | str, dict[str, Any]] = {
    **_READ_ENVELOPES,
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}
_UPLOAD_ENVELOPES: dict[int | str, dict[str, Any]] = {
    **_WRITE_ENVELOPES,
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorEnvelope},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorEnvelope},
}

# Manual request-body contract for the upload (the endpoint declares no body
# param, so FastAPI documents nothing on its own — ADR-009 + upload ruling).
_UPLOAD_REQUEST_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {
                        "type": "string",
                        "format": "binary",
                        "description": "A single static JPEG, PNG, or WebP image.",
                    }
                },
                # Exactly one file part and zero other form fields (the
                # binding upload ruling): the contract advertises that no
                # additional properties are accepted.
                "additionalProperties": False,
            }
        }
    },
}


@media_admin_router.post(
    "",
    operation_id="media_asset_upload",
    status_code=status.HTTP_201_CREATED,
    responses=_UPLOAD_ENVELOPES,
    openapi_extra={"requestBody": _UPLOAD_REQUEST_BODY},
)
async def media_asset_upload(
    business_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> MediaAssetView:
    """Upload one image; returns the stored asset (pending).

    Auth and CSRF run as dependencies (before any body parse); the handler
    then completes the pre-body gate (capability + non-locking lifecycle)
    on the request session and streams the bounded body. Multipart
    extraction, processing, object storage, and the authoritative
    transaction all run in an AnyIO worker thread — only the bounded async
    streaming stays on the event loop (final correction 2).
    """
    settings: Settings = request.app.state.settings
    storage: MediaStorage = request.app.state.media_storage
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    scratch_dir: Path = request.app.state.media_scratch_dir

    # Pre-body gate (final correction F): capability + non-locking lifecycle
    # BEFORE any body byte is parsed. Closed businesses are rejected here.
    authorize_write_nonlocking(db, actor, business_id)

    # The Content-Type header (multipart boundary) is captured on the loop;
    # the live Request object never crosses into the worker thread.
    content_type_header = request.headers.get("content-type", "")
    body = await read_bounded_body(request, file_max_bytes=settings.media_upload_max_bytes)
    try:
        return await anyio.to_thread.run_sync(
            lambda: service.process_upload(
                session_factory=session_factory,
                storage=storage,
                business_id=business_id,
                actor=actor,
                content_type_header=content_type_header,
                body=body,
                file_max_bytes=settings.media_upload_max_bytes,
                scratch_dir=scratch_dir,
            )
        )
    finally:
        body.close()


@media_admin_router.get(
    "",
    operation_id="media_assets_list",
    responses=_READ_ENVELOPES,
)
def media_assets_list(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    limit: Annotated[int, Query(ge=1, le=policies.MEDIA_LIST_PAGE_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(pending|active)$")
    ] = None,
) -> MediaAssetPage:
    """A page of the business's media assets (newest first, any member)."""
    return service.list_assets(
        db, actor, business_id, limit=limit, offset=offset, status=status_filter
    )


@media_admin_router.get(
    "/{asset_id}",
    operation_id="media_asset_get",
    responses=_READ_ENVELOPES,
)
def media_asset_get(
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> MediaAssetView:
    """One asset with its variants (any member; pending included)."""
    return service.get_asset(db, actor, business_id, asset_id)


@media_admin_router.get(
    "/{asset_id}/file/{variant}",
    operation_id="media_asset_file_get",
    response_class=StreamingResponse,
    responses={**_READ_ENVELOPES, 200: {"content": {"image/webp": {}}}},
)
def media_asset_file_get(
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    variant: str,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> StreamingResponse:
    """Authorized admin preview of one stored object (pending allowed, R7).

    Serves WebP with a fixed content type, ``nosniff``, a server-composed
    inline filename, and ``no-store`` (public caching is the M3D/M4
    decision). Missing canonical or variant → 404.
    """
    if variant != CANONICAL_VARIANT and variant not in policies.VARIANT_NAMES:
        from app.core.errors import ResourceNotFoundError

        raise ResourceNotFoundError("Media variant not found.")
    storage: MediaStorage = request.app.state.media_storage
    stream = service.open_asset_object(db, actor, business_id, asset_id, variant, storage)
    filename = f"{asset_id}-{variant}.webp"
    # Closure is guaranteed through the real StreamingResponse/ASGI lifecycle
    # by two independent mechanisms (round-2 finding 1):
    #   * the generator's own ``finally`` closes on completion, on a
    #     streaming error, and on client-disconnect cancellation
    #     (``GeneratorExit``);
    #   * a response-level ``BackgroundTask`` closes after the response, a
    #     safety net for any path where the iterator is not driven to
    #     finalization by the framework.
    # ``close`` is idempotent on file objects, so a double close is safe.
    return StreamingResponse(
        _stream_and_close(stream),
        media_type="image/webp",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
        background=BackgroundTask(stream.close),
    )


def _stream_and_close(stream: BinaryIO) -> Iterator[bytes]:
    """Yield the object in bounded chunks, always closing the handle.

    The ``finally`` runs on normal completion, on a streaming error, and on
    client disconnect (the generator is closed with ``GeneratorExit``), so
    the preview file descriptor is never leaked (final correction 5). The
    route additionally attaches a background close as a response-level
    safety net (round-2 finding 1).
    """
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        stream.close()


@media_admin_router.delete(
    "/{asset_id}",
    operation_id="media_asset_delete",
    responses=_WRITE_ENVELOPES,
)
def media_asset_delete(
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> MediaDeletedResponse:
    """Delete an asset (referenced → 409); objects removed after commit."""
    storage: MediaStorage = request.app.state.media_storage
    service.delete_asset(db, actor, business_id, asset_id, storage)
    return MediaDeletedResponse()
