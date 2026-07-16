"""Identity HTTP dependencies (M2A, ADR-010).

Dependencies *resolve context only* (approved review item R6): they
authenticate the session cookie and hand services an ``ActorContext``.
They never grant capabilities — capability enforcement lives inside
application services (from Milestone 2B).
"""

import hmac
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ApiError, ErrorCode
from app.core.settings import Settings
from app.domains.identity import service
from app.domains.identity.cookies import session_cookie_deletion_header
from app.domains.identity.exceptions import AuthenticationRequiredError
from app.domains.identity.service import ActorContext

CSRF_HEADER = "X-CSRF-Token"


def current_actor(request: Request, db: Annotated[Session, Depends(get_session)]) -> ActorContext:
    """Authenticate the session cookie or fail with 401.

    A presented-but-invalid cookie earns a deletion ``Set-Cookie`` on the
    401 so stale browsers converge instead of retrying forever (ADR-010).
    """
    settings: Settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if token is None:
        raise AuthenticationRequiredError()
    actor = service.resolve_session(db, settings, session_token=token)
    if actor is None:
        raise AuthenticationRequiredError(
            headers={"Set-Cookie": session_cookie_deletion_header(settings)}
        )
    return actor


def csrf_protected_actor(
    request: Request, actor: Annotated[ActorContext, Depends(current_actor)]
) -> ActorContext:
    """Second CSRF layer: the synchronizer token (ADR-010).

    Applied to every unsafe cookie-authenticated endpoint, independent of
    the browser-context header check.
    """
    presented = request.headers.get(CSRF_HEADER)
    if presented is None or not hmac.compare_digest(presented, actor.csrf_token):
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.CSRF_REJECTED,
            "Missing or invalid CSRF token.",
        )
    return actor
