"""Platform storefront-governance endpoint (M4B, ADR-020 §6).

Design assignment is platform authority (blueprint §12.3): it lives on
the platform prefix, requires ``platform.businesses.manage``, and is the
one storefront mutation a membership can never perform. The service owns
enforcement; the route translates. Operation IDs are permanent client
contracts (ADR-009).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor
from app.domains.storefront import service
from app.domains.storefront.schemas import DesignAssignment, DesignAssignmentResult

storefront_platform_router = APIRouter(prefix="/platform/businesses", tags=["platform"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@storefront_platform_router.put(
    "/{business_id}/design",
    operation_id="platform_business_design_set",
    responses=_ENVELOPES,
)
def platform_business_design_set(
    business_id: uuid.UUID,
    payload: DesignAssignment,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> DesignAssignmentResult:
    """Assign the draft's design variant (creates the first draft if none).

    The acknowledgment carries variant facts only — platform
    administrators hold no storefront read (§7 non-disclosure 404 on the
    business-scoped surface), so no composition content is returned here.
    """
    return service.assign_design(db, actor, business_id, payload)
