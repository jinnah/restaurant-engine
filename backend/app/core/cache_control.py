"""Response cache policy for the versioned API (M2A ADR-010; M3D ADR-017).

Every ``/api/v1`` response is ``Cache-Control: no-store`` — the API serves
session-, CSRF-, and account-bearing payloads — with exactly one approved
exception: a **successful** public media delivery.

The exception is decided here, from the request path, the request method,
and the response status. It is deliberately *not* implemented as "respect
whatever ``Cache-Control`` the route set": that would let any current or
future authenticated route opt itself out of the global policy by
accident. This middleware stays the single authority, and public media
routes set no cache header of their own.

Why one hour rather than a year, when the bytes at a URL never change:
the *bytes* are immutable (asset identity never changes in place), but the
URL's **authorization** is not. An image can be detached from its item,
hidden, deleted, or taken offline with the whole Business through
suspension. ``max-age`` is therefore the bound on how long a shared cache
may keep serving something that is no longer public — one hour, and
errors are never cacheable at all.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_PREFIX = "/api/v1"
_NO_STORE = "no-store"

# The one cacheable public surface, and the exact conditions for it. The
# prefix is the single definition of the public media path: the route, the
# URLs the menu projection composes, and this policy all derive from it, and
# a route test pins the registered path against it.
PUBLIC_MEDIA_PREFIX = "/api/v1/public/media/"
PUBLIC_MEDIA_CACHE_CONTROL = "public, max-age=3600, immutable"
_CACHEABLE_METHODS = frozenset({"GET", "HEAD"})
_CACHEABLE_STATUSES = frozenset({200, 304})


class NoStoreApiMiddleware:
    """Pure ASGI middleware stamping the approved cache policy."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(_PREFIX):
            await self.app(scope, receive, send)
            return

        cacheable_request = (
            scope["path"].startswith(PUBLIC_MEDIA_PREFIX) and scope["method"] in _CACHEABLE_METHODS
        )

        async def send_with_cache_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                cacheable = cacheable_request and message["status"] in _CACHEABLE_STATUSES
                MutableHeaders(scope=message)["Cache-Control"] = (
                    PUBLIC_MEDIA_CACHE_CONTROL if cacheable else _NO_STORE
                )
            await send(message)

        await self.app(scope, receive, send_with_cache_policy)
