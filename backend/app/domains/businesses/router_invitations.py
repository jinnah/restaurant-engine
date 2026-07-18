"""Business-scoped invitation management (M2D, ADR-014).

Owners and managers (``business.members.invite``) issue, list, and revoke
invitations for their own business, bounded by the role ceiling enforced
in the service. Routers translate only. The issuance response carries the
raw token exactly once for out-of-band delivery.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.core.settings import Settings
from app.domains.businesses import invitations
from app.domains.businesses.schemas import (
    EmptyCommand,
    InvitationCreate,
    InvitationIssueResponse,
    InvitationPage,
    InvitationRevokedResponse,
    InvitationSummary,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor

invitations_router = APIRouter(prefix="/businesses", tags=["businesses"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


def issue_response(issued: invitations.IssuedInvitation) -> InvitationIssueResponse:
    return InvitationIssueResponse(
        token=issued.token,
        invitation_id=issued.invitation_id,
        expires_at=issued.expires_at,
        email=issued.email_normalized,
        role=issued.role,
    )


def invitation_page(
    items: list[invitations.PendingInvitation], total: int, limit: int, offset: int
) -> InvitationPage:
    return InvitationPage(
        items=[
            InvitationSummary(
                invitation_id=item.invitation_id,
                email=item.email,
                role=item.role,
                created_at=item.created_at,
                expires_at=item.expires_at,
                state="pending" if item.state == "pending" else "expired",
                invited_by_user_id=item.invited_by_user_id,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@invitations_router.post(
    "/{business_id}/invitations",
    operation_id="business_invitation_create",
    status_code=status.HTTP_201_CREATED,
    responses=_ENVELOPES,
)
def business_invitation_create(
    business_id: uuid.UUID,
    payload: InvitationCreate,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> InvitationIssueResponse:
    """Invite a member (role ceiling applies; token returned once)."""
    settings: Settings = request.app.state.settings
    issued = invitations.issue_invitation(
        db,
        settings,
        actor,
        business_id,
        email=payload.email,
        role=payload.role,
        via_platform=False,
    )
    return issue_response(issued)


@invitations_router.get(
    "/{business_id}/invitations",
    operation_id="business_invitations_list",
    responses=_ENVELOPES,
)
def business_invitations_list(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvitationPage:
    """Pending invitations (history lives in the audit trail)."""
    items, total = invitations.list_pending_invitations(
        db, actor, business_id, limit=limit, offset=offset, via_platform=False
    )
    return invitation_page(items, total, limit, offset)


@invitations_router.post(
    "/{business_id}/invitations/{invitation_id}/revoke",
    operation_id="business_invitation_revoke",
    responses=_ENVELOPES,
)
def business_invitation_revoke(
    business_id: uuid.UUID,
    invitation_id: uuid.UUID,
    _command: EmptyCommand,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> InvitationRevokedResponse:
    """Revoke a pending invitation (allowed in any business status)."""
    invitations.revoke_invitation(db, actor, business_id, invitation_id, via_platform=False)
    return InvitationRevokedResponse(status="revoked")
