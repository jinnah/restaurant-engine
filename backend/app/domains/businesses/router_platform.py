"""Platform business-management endpoints (M2B).

Routers translate only (docs/02): the service enforces the platform
capability and owns the transaction. Every unsafe route carries the two
M2A CSRF layers (browser-context + synchronizer token); every route
requires an authenticated actor. Operation IDs are permanent client
contracts (ADR-009).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.businesses import service
from app.domains.businesses.schemas import (
    BusinessCreate,
    BusinessPage,
    BusinessSummary,
    EmptyCommand,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor

platform_router = APIRouter(prefix="/platform/businesses", tags=["platform"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
}
_ENVELOPES_404 = {**_ENVELOPES, status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}
_ENVELOPES_STATE = {**_ENVELOPES_404, status.HTTP_409_CONFLICT: {"model": ErrorEnvelope}}


@platform_router.post(
    "",
    operation_id="platform_businesses_create",
    status_code=status.HTTP_201_CREATED,
    responses={**_ENVELOPES, status.HTTP_409_CONFLICT: {"model": ErrorEnvelope}},
)
def platform_businesses_create(
    payload: BusinessCreate,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> BusinessSummary:
    """Create a business (starts in provisioning)."""
    return service.create_business(db, actor, payload)


@platform_router.get(
    "",
    operation_id="platform_businesses_list",
    responses=_ENVELOPES,
)
def platform_businesses_list(
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BusinessPage:
    """Bounded platform catalog page (created_at DESC, id DESC)."""
    return service.list_businesses(db, actor, limit=limit, offset=offset)


@platform_router.get(
    "/{business_id}",
    operation_id="platform_business_get",
    responses=_ENVELOPES_404,
)
def platform_business_get(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> BusinessSummary:
    """Platform read of any business."""
    return service.get_business_platform(db, actor, business_id)


@platform_router.post(
    "/{business_id}/activate",
    operation_id="platform_business_activate",
    responses=_ENVELOPES_STATE,
)
def platform_business_activate(
    business_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> BusinessSummary:
    """provisioning → active (requires at least one owner)."""
    return service.activate(db, actor, business_id)


@platform_router.post(
    "/{business_id}/suspend",
    operation_id="platform_business_suspend",
    responses=_ENVELOPES_STATE,
)
def platform_business_suspend(
    business_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> BusinessSummary:
    """active → suspended."""
    return service.suspend(db, actor, business_id)


@platform_router.post(
    "/{business_id}/reactivate",
    operation_id="platform_business_reactivate",
    responses=_ENVELOPES_STATE,
)
def platform_business_reactivate(
    business_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> BusinessSummary:
    """suspended → active."""
    return service.reactivate(db, actor, business_id)


@platform_router.post(
    "/{business_id}/close",
    operation_id="platform_business_close",
    responses=_ENVELOPES_STATE,
)
def platform_business_close(
    business_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> BusinessSummary:
    """suspended → closed (terminal)."""
    return service.close(db, actor, business_id)
