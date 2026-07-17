"""Restaurant-scoped member endpoints (M2B).

Administrative tenant resolution: the tenant comes from the route path and
is validated against the caller's membership inside the service (never a
header). Nonmembers — including platform admins, who hold no membership —
get 404 (existence non-disclosure); a suspended tenant still returns 200 so
the member can see the status (approved ruling 2).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import current_actor
from app.domains.tenants import service
from app.domains.tenants.schemas import RestaurantSummary

restaurant_router = APIRouter(prefix="/restaurants", tags=["restaurants"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


@restaurant_router.get(
    "/{restaurant_id}",
    operation_id="restaurant_get",
    responses=_ENVELOPES,
)
def restaurant_get(
    restaurant_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> RestaurantSummary:
    """Read the caller's own restaurant (requires membership)."""
    return service.get_restaurant_for_member(db, actor, restaurant_id)
