"""Authentication endpoints (M2A, ADR-010).

Routers translate only (docs/02): every workflow, transaction, and
security decision lives in the identity service; cookie mechanics live in
``cookies``; the two CSRF layers are dependencies. Operation IDs are
permanent client contracts (ADR-009).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.browser_context import require_browser_context
from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.core.settings import Settings
from app.domains.identity import service
from app.domains.identity.cookies import clear_session_cookie, set_session_cookie
from app.domains.identity.dependencies import csrf_protected_actor, current_actor
from app.domains.identity.schemas import (
    LoginRequest,
    LogoutResponse,
    SessionResponse,
    UserSummary,
)
from app.domains.identity.service import ActorContext

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_ENVELOPE_401: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope}
}
_ENVELOPE_403: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope}
}


def _session_response(user: service.AuthenticatedUser, csrf_token: str) -> SessionResponse:
    return SessionResponse(
        user=UserSummary(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_platform_admin=user.is_platform_admin,
        ),
        csrf_token=csrf_token,
    )


@auth_router.post(
    "/login",
    operation_id="auth_login",
    dependencies=[Depends(require_browser_context)],
    responses={**_ENVELOPE_401, **_ENVELOPE_403},
)
def auth_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_session)],
) -> SessionResponse:
    """Authenticate and open a fresh session (sets the session cookie)."""
    settings: Settings = request.app.state.settings
    result = service.login(db, settings, email=payload.email, password=payload.password)
    set_session_cookie(response, settings, result.session_token)
    return _session_response(result.user, result.csrf_token)


@auth_router.post(
    "/logout",
    operation_id="auth_logout",
    dependencies=[Depends(require_browser_context)],
    responses={**_ENVELOPE_401, **_ENVELOPE_403},
)
def auth_logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> LogoutResponse:
    """Revoke the current session and clear the cookie."""
    settings: Settings = request.app.state.settings
    service.logout(db, actor=actor)
    clear_session_cookie(response, settings)
    return LogoutResponse(status="logged_out")


@auth_router.get(
    "/session",
    operation_id="auth_session",
    responses={**_ENVELOPE_401},
)
def auth_session(
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> SessionResponse:
    """Current authenticated identity plus the CSRF synchronizer token."""
    return _session_response(actor.user, actor.csrf_token)
