"""Public, host-resolved order placement (M6A, ADR-026).

The Business is resolved from the request Host only (ADR-013) and the
D10 gate answers ineligibility — no ``online_ordering`` entitlement,
pickup disabled — with the same neutral 404 as an unknown host: the API
never discloses a capability the storefront page does not show.

Placement is an anonymous **unsafe** request, so it carries the
fail-closed browser-context check (ADR-010, extended by ADR-026 D9 with
self-origin acceptance for tenant hosts). It rides the global
``no-store`` response policy like every non-media API route.

Tracking, cancellation, and the public slot listing are M6B.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.browser_context import require_browser_context
from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.businesses.resolution import ResolvedBusiness, resolve_public_business
from app.domains.orders import service
from app.domains.orders.schemas import OrderPlace, OrderPlacedResponse

orders_public_router = APIRouter(prefix="/public", tags=["public"])

_PLACEMENT_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
    status.HTTP_201_CREATED: {"model": OrderPlacedResponse},
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
