"""Fail-closed browser-context check for unsafe requests (M2A, ADR-010).

Every browser-facing unsafe request must positively prove same-origin
browser context — absence of evidence is rejection, not acceptance:

1. ``Sec-Fetch-Site`` present: only ``same-origin`` passes ("none",
   "same-site", and "cross-site" are all rejected — no legitimate unsafe
   API request arrives via address bar or from a sibling origin).
2. Else ``Origin`` present: must exactly match a trusted origin.
3. Else ``Referer`` present: its origin must exactly match.
4. None of the three: **rejected**.

Modern browsers always send Sec-Fetch-* (and Origin on unsafe requests);
non-browser clients — tests, scripts, server-side callers — must send an
allowlisted ``Origin`` explicitly (docs/05). This check is one of two
independent CSRF layers; the synchronizer token (identity dependency)
is the other.
"""

from urllib.parse import urlsplit

from fastapi import Request, status

from app.core.errors import ApiError, ErrorCode


def _rejection(message: str) -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, ErrorCode.CSRF_REJECTED, message)


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def check_browser_context(request: Request) -> None:
    """Raise ``ApiError`` (403 csrf_rejected) unless same-origin is proven."""
    trusted = request.app.state.settings.trusted_origin_set

    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site is not None:
        if sec_fetch_site.strip().lower() == "same-origin":
            return
        raise _rejection("Cross-site request rejected.")

    origin = request.headers.get("origin")
    if origin is not None:
        if origin.strip().rstrip("/").lower() in trusted:
            return
        raise _rejection("Request origin is not trusted.")

    referer = request.headers.get("referer")
    if referer is not None:
        referer_origin = _origin_of(referer.strip())
        if referer_origin is not None and referer_origin in trusted:
            return
        raise _rejection("Request referrer is not trusted.")

    # Fail closed (approved review item R2): no browser-context evidence.
    raise _rejection("Request carries no browser-context evidence.")


async def require_browser_context(request: Request) -> None:
    """FastAPI dependency form of the check, for unsafe endpoints."""
    check_browser_context(request)
