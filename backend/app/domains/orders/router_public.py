"""Public, host-resolved ordering surface (M6A/M6B, ADR-026).

The Business is resolved from the request Host only (ADR-013). The D10
gate answers placement and slot-listing ineligibility — no
``online_ordering`` entitlement, pickup disabled — with the same neutral
404 as an unknown host: the API never discloses a capability the
storefront page does not show. Tracking and cancellation are
deliberately **not** entitlement-gated (D10 as amended): an order
already placed stays trackable and cancellable by token possession plus
Host after the platform revokes ordering.

The unsafe requests (placement, cancellation) carry the fail-closed
browser-context check (ADR-010, extended by ADR-026 D9 with self-origin
acceptance for tenant hosts). Everything rides the global ``no-store``
response policy.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.browser_context import require_browser_context
from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.businesses.resolution import ResolvedBusiness, resolve_public_business
from app.domains.orders import service
from app.domains.orders.schemas import (
    OrderPlace,
    OrderPlacedResponse,
    PublicOrderView,
    PublicPickupSlots,
)

orders_public_router = APIRouter(prefix="/public", tags=["public"])

_PLACEMENT_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
    status.HTTP_201_CREATED: {"model": OrderPlacedResponse},
}

_ENVELOPES_404: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}

_CANCEL_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@orders_public_router.post(
    "/orders",
    operation_id="public_order_place",
    dependencies=[Depends(require_browser_context)],
    responses=_PLACEMENT_ENVELOPES,
)
def public_order_place(
    payload: OrderPlace,
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
    response: Response,
) -> OrderPlacedResponse:
    """Place a pickup order (idempotent — blueprint §7.7, ruling D2).

    201 with the order and its tracking token on creation; 200 with the
    stored order (and an empty token — the token is disclosed exactly
    once) when the idempotency key replays. Typed 409s carry the honest
    reason: ``cart_stale``, ``price_changed``, ``slot_unavailable``, or
    ``idempotency_key_reused``.
    """
    placed, created = service.place_order(db, business, payload)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return placed


@orders_public_router.get(
    "/orders/{tracking_token}",
    operation_id="public_order_get",
    responses=_ENVELOPES_404,
)
def public_order_get(
    tracking_token: str,
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
) -> PublicOrderView:
    """The customer's order status by tracking token (M6B, ruling D4).

    Token possession plus the tenant Host, both required; every failure
    is the one neutral 404; the projection carries the stored snapshot
    and **no customer fields** (a tracking URL is shareable by design).
    """
    return service.get_order_by_token(db, business, tracking_token)


@orders_public_router.post(
    "/orders/{tracking_token}/cancel",
    operation_id="public_order_cancel",
    dependencies=[Depends(require_browser_context)],
    responses=_CANCEL_ENVELOPES,
)
def public_order_cancel(
    tracking_token: str,
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
) -> PublicOrderView:
    """Cancel a submitted order (M6B, ruling D11).

    Idempotent on an already-cancelled order; anything past
    ``submitted`` refuses with 409 ``invalid_state`` (M7's machine).
    """
    return service.cancel_by_token(db, business, tracking_token)


@orders_public_router.get(
    "/pickup-slots",
    operation_id="public_pickup_slots_get",
    responses=_ENVELOPES_404,
)
def public_pickup_slots_get(
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
) -> PublicPickupSlots:
    """The bounded valid pickup instants for the scheduled picker (M6B).

    Gated exactly like placement (ruling D10): ineligibility is the one
    neutral 404. Never cacheable — the list is time-derived.
    """
    return service.list_pickup_slots(db, business)
