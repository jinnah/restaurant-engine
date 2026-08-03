"""Business-scoped hours administration endpoints (M5A, ADR-025).

Routers translate only (docs/02): the service enforces capabilities, the
business-row lock, and the lifecycle rules. The tenant comes from the
route path and is validated against the caller's membership inside the
service — nonmembers (including platform admins, who hold no membership)
get 404. Every unsafe route carries the two M2A CSRF layers. Operation
IDs are permanent client contracts (ADR-009).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.hours import service
from app.domains.hours.schemas import (
    AvailabilityPreview,
    FulfillmentSet,
    HoursDeletedResponse,
    HoursSettings,
    OrderingPauseSet,
    ScheduleExceptionSet,
    WeeklyScheduleSet,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor

hours_admin_router = APIRouter(prefix="/businesses/{business_id}/hours", tags=["hours"])

_READ_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}
_WRITE_ENVELOPES: dict[int | str, dict[str, Any]] = {
    **_READ_ENVELOPES,
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@hours_admin_router.get(
    "",
    operation_id="hours_settings_get",
    responses=_READ_ENVELOPES,
)
def hours_settings_get(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> HoursSettings:
    """The complete operating configuration in one read."""
    return service.get_hours(db, actor, business_id)


@hours_admin_router.get(
    "/preview",
    operation_id="hours_availability_preview",
    responses=_READ_ENVELOPES,
)
def hours_availability_preview(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    at: Annotated[datetime | None, Query()] = None,
) -> AvailabilityPreview:
    """The computed availability at ``at`` (default: now) — a member probe."""
    return service.preview_availability(db, actor, business_id, at)


@hours_admin_router.put(
    "/weekly",
    operation_id="hours_weekly_set",
    responses=_WRITE_ENVELOPES,
)
def hours_weekly_set(
    business_id: uuid.UUID,
    payload: WeeklyScheduleSet,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> HoursSettings:
    """Replace the whole weekly schedule (idempotent full replacement)."""
    return service.set_weekly_schedule(db, actor, business_id, payload)


@hours_admin_router.put(
    "/exceptions/{exception_date}",
    operation_id="hours_exception_set",
    responses=_WRITE_ENVELOPES,
)
def hours_exception_set(
    business_id: uuid.UUID,
    exception_date: date,
    payload: ScheduleExceptionSet,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> HoursSettings:
    """Create or replace one date's override (empty intervals = closed)."""
    return service.set_schedule_exception(db, actor, business_id, exception_date, payload)


@hours_admin_router.delete(
    "/exceptions/{exception_date}",
    operation_id="hours_exception_delete",
    responses=_WRITE_ENVELOPES,
)
def hours_exception_delete(
    business_id: uuid.UUID,
    exception_date: date,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> HoursDeletedResponse:
    """Remove one date's override; the weekly schedule resumes."""
    service.remove_schedule_exception(db, actor, business_id, exception_date)
    return HoursDeletedResponse()


@hours_admin_router.put(
    "/fulfillment",
    operation_id="hours_fulfillment_set",
    responses=_WRITE_ENVELOPES,
)
def hours_fulfillment_set(
    business_id: uuid.UUID,
    payload: FulfillmentSet,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> HoursSettings:
    """Write the complete fulfillment policy (full-document command)."""
    return service.set_fulfillment(db, actor, business_id, payload)


@hours_admin_router.put(
    "/pause",
    operation_id="hours_ordering_pause_set",
    responses=_WRITE_ENVELOPES,
)
def hours_ordering_pause_set(
    business_id: uuid.UUID,
    payload: OrderingPauseSet,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> HoursSettings:
    """Pause or resume ordering (M7A, ADR-027 D8) — its own command."""
    return service.set_ordering_pause(db, actor, business_id, payload)
