"""Audit list endpoints (M2D, ADR-014) — application-layer composition.

Authorization is enforced here (platform capability / membership
capability) because the audit domain must not import identity; the safe
per-action projection lives in ``audit_view``. Records are immutable
through the API — these are the only audit routes, and they are GET-only.

Filtering/pagination contract (correction H): exclusive ``before_id``
cursor on ``id DESC``; ``limit`` 1-100 (default 50); ``action`` must be a
registered audit action (unknown → 422); time filters must be UTC-aware
and ``occurred_after`` must precede ``occurred_before`` (else 422).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.api.audit_view import AuditEventPage, build_page
from app.core.database import get_session
from app.core.errors import ApiError, ErrorCode, ErrorEnvelope
from app.domains.audit import queries
from app.domains.audit.actions import AuditAction
from app.domains.identity.actor import ActorContext
from app.domains.identity.authorization import require_membership_capability
from app.domains.identity.dependencies import current_actor
from app.domains.identity.policies import Capability, require_platform_capability

audit_platform_router = APIRouter(prefix="/platform/audit-events", tags=["platform"])
audit_business_router = APIRouter(prefix="/businesses", tags=["businesses"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}

_LimitQuery = Annotated[int, Query(ge=1, le=100)]
_BeforeIdQuery = Annotated[int | None, Query(gt=0)]


def _validate_time_range(
    occurred_after: AwareDatetime | None, occurred_before: AwareDatetime | None
) -> None:
    if occurred_after is not None and occurred_before is not None:
        if occurred_after >= occurred_before:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                ErrorCode.VALIDATION_ERROR,
                "occurred_after must be earlier than occurred_before.",
            )


@audit_platform_router.get(
    "",
    operation_id="platform_audit_events_list",
    responses=_ENVELOPES,
)
def platform_audit_events_list(
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    limit: _LimitQuery = 50,
    before_id: _BeforeIdQuery = None,
    action: Annotated[AuditAction | None, Query()] = None,
    occurred_after: Annotated[AwareDatetime | None, Query()] = None,
    occurred_before: Annotated[AwareDatetime | None, Query()] = None,
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    business_id: Annotated[uuid.UUID | None, Query()] = None,
) -> AuditEventPage:
    """Platform-wide audit stream (``platform.audit.read``)."""
    require_platform_capability(actor, Capability.PLATFORM_AUDIT_READ)
    _validate_time_range(occurred_after, occurred_before)
    events = queries.platform_page(
        db,
        limit=limit,
        before_id=before_id,
        action=action.value if action is not None else None,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        actor_user_id=actor_user_id,
        business_id=business_id,
    )
    return build_page(events, limit=limit)


@audit_business_router.get(
    "/{business_id}/audit-events",
    operation_id="business_audit_events_list",
    responses=_ENVELOPES,
)
def business_audit_events_list(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    limit: _LimitQuery = 50,
    before_id: _BeforeIdQuery = None,
    action: Annotated[AuditAction | None, Query()] = None,
    occurred_after: Annotated[AwareDatetime | None, Query()] = None,
    occurred_before: Annotated[AwareDatetime | None, Query()] = None,
) -> AuditEventPage:
    """This business's audit trail (owner/manager via ``business.audit.read``;
    platform-level events are structurally excluded)."""
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_AUDIT_READ
    )
    _validate_time_range(occurred_after, occurred_before)
    events = queries.business_page(
        db,
        business_id=business_id,
        limit=limit,
        before_id=before_id,
        action=action.value if action is not None else None,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )
    return build_page(events, limit=limit)
