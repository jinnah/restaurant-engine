"""Password-recovery endpoints (M2D, ADR-014).

Two surfaces with deliberately different trust models:

* ``POST /platform/password-resets`` — authenticated + CSRF, gated by
  ``platform.users.recover`` (account-takeover-equivalent authority; every
  issuance is audited). Returns the raw token exactly once.
* ``POST /password-resets/redeem`` — public; possession of the
  high-entropy token is the authorization (docs/04 sanctioned exception 2).
  Carries the login-style browser-context check. Every failure mode is the
  same neutral 404.

Routers translate only; the recovery service owns transactions, locking,
and the two-phase Argon2 design.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.browser_context import require_browser_context
from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.core.settings import Settings
from app.domains.identity import recovery
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor
from app.domains.identity.schemas import (
    PasswordResetIssueRequest,
    PasswordResetIssueResponse,
    PasswordResetRedeemRequest,
    PasswordResetRedeemResponse,
)

recovery_public_router = APIRouter(prefix="/password-resets", tags=["recovery"])
recovery_platform_router = APIRouter(prefix="/platform/password-resets", tags=["platform"])

_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@recovery_platform_router.post(
    "",
    operation_id="platform_password_reset_issue",
    status_code=status.HTTP_201_CREATED,
    responses=_ENVELOPES,
)
def platform_password_reset_issue(
    payload: PasswordResetIssueRequest,
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> PasswordResetIssueResponse:
    """Issue a single-use reset token for an account (returned once)."""
    settings: Settings = request.app.state.settings
    issued = recovery.issue_reset(db, settings, actor, email=payload.email)
    return PasswordResetIssueResponse(
        token=issued.token, expires_at=issued.expires_at, email=issued.email_normalized
    )


@recovery_public_router.post(
    "/redeem",
    operation_id="password_reset_redeem",
    dependencies=[Depends(require_browser_context)],
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}},
)
def password_reset_redeem(
    payload: PasswordResetRedeemRequest,
    db: Annotated[Session, Depends(get_session)],
) -> PasswordResetRedeemResponse:
    """Redeem a reset token: set the password, revoke every session."""
    recovery.redeem_reset(db, token=payload.token, new_password=payload.new_password)
    return PasswordResetRedeemResponse(status="password_reset")
