"""Public (unauthenticated) menu endpoint (M3D, ADR-017).

The Business is resolved from the request Host by the shared M2C resolver
(never a path, query, header, or cookie), so this route takes no tenant
argument and every resolution failure renders as the neutral 404 contract.
No session and no CSRF token are involved.

The ``HEAD`` companion is registered on the same handler with
``include_in_schema=False``: this FastAPI version does not add ``HEAD`` to
an ``APIRoute``'s methods, and declaring it as a method would emit a second
OpenAPI operation reusing the same ``operation_id``. A schema-hidden
companion keeps the generated client and the pinned operation count
untouched while making ``HEAD`` behave exactly like ``GET`` (the response
body is discarded by the server, as HTTP requires).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.businesses.resolution import ResolvedBusiness, resolve_public_business
from app.domains.catalog import public_service
from app.domains.catalog.public_schemas import PublicMenu

catalog_public_router = APIRouter(prefix="/public", tags=["public"])

_ENVELOPES_404: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


@catalog_public_router.head("/menu", include_in_schema=False)
@catalog_public_router.get("/menu", operation_id="public_menu_get", responses=_ENVELOPES_404)
def public_menu_get(
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
) -> PublicMenu:
    """The public menu of the Business resolved from the Host.

    Hidden items and invisible categories are excluded, categories with no
    publicly visible item are omitted, and unavailable modifier options and
    unsatisfiable groups are dropped. Prices are integer minor units in the
    business's own currency.
    """
    return public_service.get_public_menu(db, business)
