"""Session cookie contract (M2A, ADR-010).

One module owns every attribute of the session cookie so setting and
clearing can never drift apart — a deletion must repeat the exact
name/Path/Secure attributes to match, especially under the production
``__Host-`` prefix.

The cookie is persistent (Max-Age = absolute session lifetime); server-side
idle/absolute/revocation checks are always authoritative, so a cookie that
outlives its session is harmless and is actively cleared on the first
rejected request.
"""

from fastapi import Response

from app.core.settings import Settings


def _absolute_max_age_seconds(settings: Settings) -> int:
    return settings.session_absolute_lifetime_days * 24 * 60 * 60


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=_absolute_max_age_seconds(settings),
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def session_cookie_deletion_header(settings: Settings) -> str:
    """The deletion Set-Cookie value, for error paths that bypass Response.

    Used when authentication fails inside a dependency and the 401 envelope
    is produced by the ApiError handler rather than an endpoint response.
    """
    parts = [
        f"{settings.session_cookie_name}=",
        "Max-Age=0",
        "Path=/",
        "HttpOnly",
        "SameSite=lax",
    ]
    if settings.session_cookie_secure:
        parts.append("Secure")
    return "; ".join(parts)
