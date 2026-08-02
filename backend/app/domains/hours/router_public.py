"""Public, host-resolved availability projection (M5B, ADR-025).

The Business is resolved from the request Host only (M2C, ADR-013 —
never a path, query, header, or cookie), so this route takes no tenant
argument. Every active Business has an availability — one with no
configured hours is honestly closed with nothing upcoming, because an
empty schedule is a real operational state, not an error. Unknown,
provisioning, suspended, closed, reserved, and malformed hosts are the
same neutral 404.

Responses are deliberately **never** publicly cacheable (ruling D4): the
body is time-derived, and a sixty-second grant would make "Open now"
wrong at exactly the boundaries a customer checks. No entry is added to
the cache-control middleware's grant map, so the global ``no-store``
default applies — to successes and errors alike.

A schema-hidden ``HEAD`` companion mirrors the public-menu convention:
same handler, same resolution, same neutral failure contract, absent
from the OpenAPI document so the operation count is unchanged.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.businesses.resolution import ResolvedBusiness, resolve_public_business
from app.domains.hours import public_service
from app.domains.hours.public_schemas import PublicAvailability

hours_public_router = APIRouter(prefix="/public", tags=["public"])

_ENVELOPES_404: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


@hours_public_router.head("/availability", include_in_schema=False)
@hours_public_router.get(
    "/availability", operation_id="public_availability_get", responses=_ENVELOPES_404
)
def public_availability_get(
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
) -> PublicAvailability:
    """The structured hours and instant facts of the Host-resolved Business.

    Weekly schedule, upcoming exceptions, open/closed status with the
    current close or next opening, and the pickup facts — all derived
    from structured settings through the pure hours core (the Milestone
    5 exit criterion, literally).
    """
    return public_service.assemble_availability(db, business)
