"""Business-scoped member endpoints (M2B).

Administrative tenant resolution: the tenant comes from the route path and
is validated against the caller's membership inside the service (never a
header). Nonmembers — including platform admins, who hold no membership —
get 404 (existence non-disclosure); a suspended business still returns 200
so the member can see the status (approved ruling 2).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.businesses import service
from app.domains.businesses.schemas import BusinessSummary
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import current_actor

business_router = APIRouter(prefix="/businesses", tags=["businesses"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


@business_router.get(
    "/{business_id}",
    operation_id="business_get",
    responses=_ENVELOPES,
)
def business_get(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> BusinessSummary:
    """Read the caller's own business (requires membership)."""
    return service.get_business_for_member(db, actor, business_id)
