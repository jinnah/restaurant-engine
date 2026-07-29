"""Public, host-resolved storefront projection (M4C, ADR-020).

The Business is resolved from the request Host only (M2C, ADR-013 —
never a path, query, header, or cookie), so this route takes no tenant
argument. Only an **active** Business with a **currently published**
storefront version has a projection; a business that has never published
— including one holding only a draft — is the same neutral 404 as an
unknown host, so the response discloses nothing about drafts or state.

The draft is never reachable here under any input: the only row this
route reads is the ``state='published'`` singleton (ruling R-1).

A schema-hidden ``HEAD`` companion mirrors the public-menu convention:
same handler, same resolution, same neutral failure contract, absent from
the OpenAPI document so the operation count is unchanged.

Successful responses are publicly cacheable for sixty seconds — granted
by route identity in ``NoStoreApiMiddleware`` (ADR-020 §12), never by a
header this route sets. Every error, including the neutral 404, stays
``no-store``.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope, ResourceNotFoundError
from app.domains.businesses.resolution import ResolvedBusiness, resolve_public_business
from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.media.public_service import public_media_url
from app.domains.storefront import public_service, repository
from app.domains.storefront.public_schemas import PublicStorefront

storefront_public_router = APIRouter(prefix="/public", tags=["public"])

_ENVELOPES_404: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


@storefront_public_router.head("/storefront", include_in_schema=False)
@storefront_public_router.get(
    "/storefront", operation_id="public_storefront_get", responses=_ENVELOPES_404
)
def public_storefront_get(
    business: Annotated[ResolvedBusiness, Depends(resolve_public_business)],
    db: Annotated[Session, Depends(get_session)],
) -> PublicStorefront:
    """The published storefront of the Business resolved from the Host.

    Enabled sections of the currently published version, in display
    order, with media resolved to public URL descriptors. A business
    without a published version is the neutral not-found response.
    """
    row = repository.get_published(db, business_id=business.business_id)
    if row is None:
        raise ResourceNotFoundError()
    try:
        return public_service.assemble_storefront(
            db,
            business_id=business.business_id,
            summary=PublicSiteSummary(
                name=business.name,
                slug=business.slug,
                timezone=business.timezone,
                currency=business.currency,
            ),
            row=row,
            url_builder=public_media_url,
        )
    except (ValidationError, ValueError):
        # An unrenderable *published* row is an integrity defect (M4B
        # completion 1): record the bounded anomaly, then let it propagate
        # to the opaque internal-error boundary — details are logged,
        # never disclosed (ruling R-6).
        public_service.warn_config_invalid(business.business_id, "public_projection")
        raise
