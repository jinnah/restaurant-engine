"""Platform restaurant-management endpoints (M2B).

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
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor
from app.domains.tenants import service
from app.domains.tenants.schemas import (
    EmptyCommand,
    RestaurantCreate,
    RestaurantPage,
    RestaurantSummary,
)

platform_router = APIRouter(prefix="/platform/restaurants", tags=["platform"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
}
_ENVELOPES_404 = {**_ENVELOPES, status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}
_ENVELOPES_STATE = {**_ENVELOPES_404, status.HTTP_409_CONFLICT: {"model": ErrorEnvelope}}


@platform_router.post(
    "",
    operation_id="platform_restaurants_create",
    status_code=status.HTTP_201_CREATED,
    responses={**_ENVELOPES, status.HTTP_409_CONFLICT: {"model": ErrorEnvelope}},
)
def platform_restaurants_create(
    payload: RestaurantCreate,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> RestaurantSummary:
    """Create a restaurant (starts in provisioning)."""
    return service.create_restaurant(db, actor, payload)


@platform_router.get(
    "",
    operation_id="platform_restaurants_list",
    responses=_ENVELOPES,
)
def platform_restaurants_list(
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RestaurantPage:
    """Bounded platform catalog page (created_at DESC, id DESC)."""
    return service.list_restaurants(db, actor, limit=limit, offset=offset)


@platform_router.get(
    "/{restaurant_id}",
    operation_id="platform_restaurant_get",
    responses=_ENVELOPES_404,
)
def platform_restaurant_get(
    restaurant_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> RestaurantSummary:
    """Platform read of any restaurant."""
    return service.get_restaurant_platform(db, actor, restaurant_id)


@platform_router.post(
    "/{restaurant_id}/activate",
    operation_id="platform_restaurant_activate",
    responses=_ENVELOPES_STATE,
)
def platform_restaurant_activate(
    restaurant_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> RestaurantSummary:
    """provisioning → active (requires at least one owner)."""
    return service.activate(db, actor, restaurant_id)


@platform_router.post(
    "/{restaurant_id}/suspend",
    operation_id="platform_restaurant_suspend",
    responses=_ENVELOPES_STATE,
)
def platform_restaurant_suspend(
    restaurant_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> RestaurantSummary:
    """active → suspended."""
    return service.suspend(db, actor, restaurant_id)


@platform_router.post(
    "/{restaurant_id}/reactivate",
    operation_id="platform_restaurant_reactivate",
    responses=_ENVELOPES_STATE,
)
def platform_restaurant_reactivate(
    restaurant_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> RestaurantSummary:
    """suspended → active."""
    return service.reactivate(db, actor, restaurant_id)


@platform_router.post(
    "/{restaurant_id}/close",
    operation_id="platform_restaurant_close",
    responses=_ENVELOPES_STATE,
)
def platform_restaurant_close(
    restaurant_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> RestaurantSummary:
    """suspended → closed (terminal)."""
    return service.close(db, actor, restaurant_id)
