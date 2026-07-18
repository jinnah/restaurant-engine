"""Public invitation redemption endpoints (M2D, ADR-014).

Possession of the high-entropy token is the authorization (docs/04
sanctioned exception 2); tokens travel only in POST bodies — never URLs.
Public unsafe endpoints carry the login-style browser-context check;
``accept-existing`` is cookie-authenticated and therefore carries the full
CSRF regime. Every invalid-token condition returns the same neutral 404.
No acceptance path logs the caller in (approved: no auto-login).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.browser_context import require_browser_context
from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.businesses import invitations
from app.domains.businesses.schemas import (
    InvitationAcceptedResponse,
    InvitationAcceptExistingRequest,
    InvitationAcceptRequest,
    InvitationPreviewRequest,
    InvitationPreviewResponse,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor

onboarding_router = APIRouter(prefix="/invitations", tags=["onboarding"])

_ENVELOPE_404: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}
}


@onboarding_router.post(
    "/preview",
    operation_id="invitation_preview",
    dependencies=[Depends(require_browser_context)],
    responses=_ENVELOPE_404,
)
def invitation_preview(
    payload: InvitationPreviewRequest,
    db: Annotated[Session, Depends(get_session)],
) -> InvitationPreviewResponse:
    """Accept-page context: business name, role, and a masked email hint."""
    preview = invitations.preview_invitation(db, token=payload.token)
    return InvitationPreviewResponse(
        business_name=preview.business_name,
        role=preview.role,
        email_hint=preview.email_hint,
    )


@onboarding_router.post(
    "/accept",
    operation_id="invitation_accept",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_browser_context)],
    responses=_ENVELOPE_404,
)
def invitation_accept(
    payload: InvitationAcceptRequest,
    db: Annotated[Session, Depends(get_session)],
) -> InvitationAcceptedResponse:
    """Create the invited account + membership (no auto-login)."""
    accepted = invitations.accept_invitation_new_user(
        db,
        token=payload.token,
        display_name=payload.display_name,
        password=payload.password,
    )
    return InvitationAcceptedResponse(
        status="accepted",
        business_id=accepted.business_id,
        email=accepted.email_normalized,
        role=accepted.role,
    )


@onboarding_router.post(
    "/accept-existing",
    operation_id="invitation_accept_existing",
    responses={
        **_ENVELOPE_404,
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
        status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
        status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
    },
)
def invitation_accept_existing(
    payload: InvitationAcceptExistingRequest,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> InvitationAcceptedResponse:
    """Add the invited membership to the authenticated caller's account.

    The supported path for one user to belong to multiple businesses; the
    caller's email must match the invitation's.
    """
    accepted = invitations.accept_invitation_existing_user(db, actor, token=payload.token)
    return InvitationAcceptedResponse(
        status="accepted",
        business_id=accepted.business_id,
        email=accepted.email_normalized,
        role=accepted.role,
    )
