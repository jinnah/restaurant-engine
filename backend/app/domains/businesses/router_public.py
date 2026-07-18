"""Public (unauthenticated) storefront endpoints (M2C, ADR-013).

The Business is resolved from the request Host by the resolver dependency
(never a path/query/header/cookie). These routes require no session and no
CSRF token. Every resolution failure renders as the neutral 404 contract
via ``ResourceNotFoundError``. Content beyond the Business summary (menu,
storefront composition) arrives in later milestones.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.core.errors import ErrorEnvelope
from app.domains.businesses.resolution import ResolvedBusiness, resolve_public_business
from app.domains.businesses.schemas import PublicSiteSummary

public_router = APIRouter(prefix="/public", tags=["public"])

_ENVELOPES_404: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


@public_router.get("/site", operation_id="public_site_get", responses=_ENVELOPES_404)
def public_site_get(
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
) -> PublicSiteSummary:
    """Minimal public summary of the Business resolved from the Host."""
    return PublicSiteSummary(
        name=business.name,
        slug=business.slug,
        timezone=business.timezone,
        currency=business.currency,
    )
