"""Composition router for the enriched session view (M2B, decision 4).

Hosts ``GET /api/v1/auth/session`` (operation_id ``auth_session``, unchanged
from M2A) at the application layer, because its response joins identity and
businesses. login/logout remain in the identity domain router.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.session_view import SessionView, build_session_view
from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import current_actor

session_router = APIRouter(prefix="/auth", tags=["auth"])

_ENVELOPE_401: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope}
}


@session_router.get(
    "/session",
    operation_id="auth_session",
    responses=_ENVELOPE_401,
)
def auth_session(
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> SessionView:
    """Current identity, CSRF token, and the caller's business memberships."""
    return build_session_view(db, actor)
