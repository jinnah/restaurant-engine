"""Business-scoped order operations endpoints (M7A, ADR-027).

Routers translate only (docs/02): the service enforces the D2 capability
(`business.orders.operate` — reads and commands alike; this surface
carries customer PII), the D1 order-row lock, and the D3 Business lock
on the slot-releasing commands. Every transition is a named command —
status is never patched. Unsafe routes carry the two M2A CSRF layers.
Operation IDs are permanent client contracts (ADR-009).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor
from app.domains.orders import policies, service
from app.domains.orders.lifecycle import OrderStatus
from app.domains.orders.schemas import (
    AdminOrderDetail,
    AdminOrderList,
    OrderEstimateSet,
    OrderMetrics,
)

orders_admin_router = APIRouter(prefix="/businesses/{business_id}/orders", tags=["orders"])

_READ_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}
_WRITE_ENVELOPES: dict[int | str, dict[str, Any]] = {
    **_READ_ENVELOPES,
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@orders_admin_router.get(
    "",
    operation_id="orders_admin_list",
    responses=_READ_ENVELOPES,
)
def orders_admin_list(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    order_status: Annotated[list[OrderStatus] | None, Query(alias="status")] = None,
    placed_after: Annotated[datetime | None, Query()] = None,
    placed_before: Annotated[datetime | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=policies.LIST_QUERY_MAX_LENGTH)] = None,
    before_number: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[
        int, Query(ge=1, le=policies.LIST_MAX_PAGE_SIZE)
    ] = policies.LIST_DEFAULT_PAGE_SIZE,
) -> AdminOrderList:
    """One newest-first page: filters, search, exclusive id cursor (D6)."""
    return service.list_orders_admin(
        db,
        actor,
        business_id,
        statuses=order_status,
        placed_after=placed_after,
        placed_before=placed_before,
        q=q,
        before_number=before_number,
        limit=limit,
    )


@orders_admin_router.get(
    "/metrics",
    operation_id="orders_admin_metrics",
    responses=_READ_ENVELOPES,
)
def orders_admin_metrics(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> OrderMetrics:
    """Today's operational metrics, computed live (D11)."""
    return service.order_metrics(db, actor, business_id)


@orders_admin_router.get(
    "/{order_id}",
    operation_id="order_admin_get",
    responses=_READ_ENVELOPES,
)
def order_admin_get(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> AdminOrderDetail:
    """The full operational projection with the status timeline (D6)."""
    return service.get_order_admin(db, actor, business_id, order_id)


@orders_admin_router.post(
    "/{order_id}/accept",
    operation_id="order_accept",
    responses=_WRITE_ENVELOPES,
)
def order_accept(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminOrderDetail:
    """Accept a submitted order (D1)."""
    return service.transition_order(db, actor, business_id, order_id, "accept")


@orders_admin_router.post(
    "/{order_id}/reject",
    operation_id="order_reject",
    responses=_WRITE_ENVELOPES,
)
def order_reject(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminOrderDetail:
    """Reject a submitted order; its pickup slot is released (D1/D3/D5)."""
    return service.transition_order(db, actor, business_id, order_id, "reject")


@orders_admin_router.post(
    "/{order_id}/start-preparing",
    operation_id="order_start_preparing",
    responses=_WRITE_ENVELOPES,
)
def order_start_preparing(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminOrderDetail:
    """Move an accepted order to preparing (D1)."""
    return service.transition_order(db, actor, business_id, order_id, "start-preparing")


@orders_admin_router.post(
    "/{order_id}/mark-ready",
    operation_id="order_mark_ready",
    responses=_WRITE_ENVELOPES,
)
def order_mark_ready(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminOrderDetail:
    """Mark a preparing order ready for pickup (D1)."""
    return service.transition_order(db, actor, business_id, order_id, "mark-ready")


@orders_admin_router.post(
    "/{order_id}/complete",
    operation_id="order_complete",
    responses=_WRITE_ENVELOPES,
)
def order_complete(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminOrderDetail:
    """Complete a ready order at pickup (D1)."""
    return service.transition_order(db, actor, business_id, order_id, "complete")


@orders_admin_router.post(
    "/{order_id}/cancel",
    operation_id="order_cancel_by_member",
    responses=_WRITE_ENVELOPES,
)
def order_cancel_by_member(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminOrderDetail:
    """Cancel a submitted order as a member (D4); the slot is released."""
    return service.transition_order(db, actor, business_id, order_id, "cancel")


@orders_admin_router.put(
    "/{order_id}/estimate",
    operation_id="order_estimate_set",
    responses=_WRITE_ENVELOPES,
)
def order_estimate_set(
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: OrderEstimateSet,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminOrderDetail:
    """Set or clear the prep estimate while accepted/preparing (D7)."""
    return service.set_estimate(db, actor, business_id, order_id, payload)
