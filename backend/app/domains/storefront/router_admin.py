"""Business-scoped storefront administration endpoints (M4B, ADR-020).

Routers translate only (docs/02): the service enforces the storefront
capabilities, the Business row lock, and the lifecycle rules. The tenant
comes from the route path and is validated against the caller's
membership inside the service — nonmembers (including platform admins,
who hold no membership) get 404, and members lacking the capability get
403, which on this surface includes every staff read (§7). Every unsafe
route carries the two M2A CSRF layers. Operation IDs are permanent
client contracts (ADR-009).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor
from app.domains.storefront import service
from app.domains.storefront.schemas import (
    DraftPut,
    DraftView,
    PublishRequest,
    RestoreRequest,
    StorefrontOverview,
    VersionDetail,
    VersionPage,
)

storefront_admin_router = APIRouter(
    prefix="/businesses/{business_id}/storefront", tags=["storefront"]
)

# Unlike catalog, storefront reads can be denied to a same-tenant member
# (staff hold no storefront capability), so 403 belongs on reads too.
_READ_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}
_WRITE_ENVELOPES: dict[int | str, dict[str, Any]] = {
    **_READ_ENVELOPES,
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@storefront_admin_router.get(
    "",
    operation_id="storefront_get",
    responses=_READ_ENVELOPES,
)
def storefront_get(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> StorefrontOverview:
    """The storefront overview — the draft's only read representation.

    ``draft: null`` is the valid first-use absence (reads never create
    state, §5.1).
    """
    return service.get_overview(db, actor, business_id)


@storefront_admin_router.put(
    "/draft",
    operation_id="storefront_draft_put",
    responses=_WRITE_ENVELOPES,
)
def storefront_draft_put(
    business_id: uuid.UUID,
    payload: DraftPut,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> DraftView:
    """Create or replace the draft (full document, explicit intent, D-5)."""
    return service.put_draft(db, actor, business_id, payload)


@storefront_admin_router.post(
    "/publish",
    operation_id="storefront_publish",
    responses=_WRITE_ENVELOPES,
)
def storefront_publish(
    business_id: uuid.UUID,
    payload: PublishRequest,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> StorefrontOverview:
    """Publish the draft (owner only): promote, archive, seed — atomically."""
    return service.publish(db, actor, business_id, payload)


@storefront_admin_router.get(
    "/versions",
    operation_id="storefront_versions_list",
    responses=_READ_ENVELOPES,
)
def storefront_versions_list(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VersionPage:
    """Owner-facing history: the published + archived versions, newest first."""
    return service.list_versions(db, actor, business_id, limit=limit, offset=offset)


@storefront_admin_router.get(
    "/versions/{version_id}",
    operation_id="storefront_version_get",
    responses=_READ_ENVELOPES,
)
def storefront_version_get(
    business_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> VersionDetail:
    """One history row with its composition — never the draft (404 there)."""
    return service.get_version_detail(db, actor, business_id, version_id)


@storefront_admin_router.post(
    "/versions/{version_id}/restore",
    operation_id="storefront_version_restore",
    responses=_WRITE_ENVELOPES,
)
def storefront_version_restore(
    business_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: RestoreRequest,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> DraftView:
    """Restore an archived version into the draft (owner only, archived-only
    sources); returns the updated draft representation."""
    return service.restore_version(db, actor, business_id, version_id, payload)
