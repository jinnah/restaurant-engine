"""Response cache policy for the versioned API (M2A ADR-010; M3D ADR-017).

Every ``/api/v1`` response is ``Cache-Control: no-store``, with exactly one
approved exception: a **successful** public media delivery.

The exception is granted on three conditions, all required: the request
method is ``GET`` or ``HEAD``, the response status is 200 or 304, and the
response came from **the exact registered public media-file route**. That
last condition is decided by route *identity* — the resolved endpoint
object Starlette records in the ASGI scope — not by matching the request
path. A path prefix would silently extend immutable public caching to any
future sibling route beneath it; an endpoint reference cannot, because
only the one registered handler is ever that object.

It is also deliberately **not** implemented as "respect whatever
``Cache-Control`` the route set": that would let any current or future
authenticated route opt itself out of the global policy by accident. This
middleware stays the single authority, and the public media route sets no
cache header of its own.

Why one hour rather than a year, when the bytes at a URL never change:
the *bytes* are immutable (asset identity never changes in place), but the
URL's **authorization** is not. An image can be detached from its item,
hidden, deleted, or taken offline with the whole Business through
suspension. ``max-age`` is therefore the bound on how long a shared cache
may keep serving something that is no longer public — one hour, and
errors are never cacheable at all.
"""

from collections.abc import Callable
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_PREFIX = "/api/v1"
_NO_STORE = "no-store"

PUBLIC_MEDIA_CACHE_CONTROL = "public, max-age=3600, immutable"
_CACHEABLE_METHODS = frozenset({"GET", "HEAD"})
_CACHEABLE_STATUSES = frozenset({200, 304})


class NoStoreApiMiddleware:
    """Pure ASGI middleware stamping the approved cache policy.

    ``cacheable_endpoint`` is the one handler whose successful responses
    may be publicly cached. The application factory supplies it, so this
    module needs no knowledge of routers or URL shapes, and a route that
    was never wired here can never become cacheable.
    """

    def __init__(self, app: ASGIApp, *, cacheable_endpoint: Callable[..., Any]) -> None:
        self.app = app
        self._cacheable_endpoint = cacheable_endpoint

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(_PREFIX):
            await self.app(scope, receive, send)
            return

        cacheable_method = scope["method"] in _CACHEABLE_METHODS

        async def send_with_cache_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                # ``endpoint`` is written into the scope by routing, so it is
                # populated by the time a response starts; an unmatched path
                # has none at all. Identity comparison means a lookalike
                # path, a sibling route, or a future route under the same
                # prefix can never satisfy it.
                cacheable = (
                    cacheable_method
                    and message["status"] in _CACHEABLE_STATUSES
                    and scope.get("endpoint") is self._cacheable_endpoint
                )
                MutableHeaders(scope=message)["Cache-Control"] = (
                    PUBLIC_MEDIA_CACHE_CONTROL if cacheable else _NO_STORE
                )
            await send(message)

        await self.app(scope, receive, send_with_cache_policy)
