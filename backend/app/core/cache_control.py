"""Response cache policy for the versioned API (M2A ADR-010; M3D ADR-017;
M4C ADR-020).

Every ``/api/v1`` response is ``Cache-Control: no-store``, with exactly two
approved exceptions:

* a **successful** public media delivery (M3D): ``GET``/``HEAD``, status
  200 or 304, from the one registered public media-file route —
  ``public, max-age=3600, immutable``;
* a **successful** public storefront projection (M4C): ``GET``/``HEAD``,
  status 200, from the one registered public storefront route —
  ``public, max-age=60``. Sixty seconds is the approved maximum
  visitor-visible staleness and post-suspension exposure (ADR-020 §12);
  the projection is not immutable — publication replaces it in place —
  so no ``immutable`` and no validator-based caching are granted.

An exception is granted only when all three conditions hold: the request
method is ``GET`` or ``HEAD``, the response status is in the policy's
approved set, and the response came from **the exact registered endpoint**.
That last condition is decided by route *identity* — the resolved endpoint
object Starlette records in the ASGI scope — not by matching the request
path. A path prefix would silently extend public caching to any future
sibling route beneath it; an endpoint reference cannot, because only the
one registered handler is ever that object.

It is also deliberately **not** implemented as "respect whatever
``Cache-Control`` the route set": that would let any current or future
authenticated route opt itself out of the global policy by accident. This
middleware stays the single authority, and neither cacheable route sets a
cache header of its own.

Why one hour for media rather than a year, when the bytes at a URL never
change: the *bytes* are immutable (asset identity never changes in place),
but the URL's **authorization** is not. An image can be detached from its
item, removed from a published storefront, deleted, or taken offline with
the whole Business through suspension. ``max-age`` is therefore the bound
on how long a shared cache may keep serving something that is no longer
public — one hour for media, one minute for the storefront projection, and
errors are never cacheable at all.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_PREFIX = "/api/v1"
_NO_STORE = "no-store"

PUBLIC_MEDIA_CACHE_CONTROL = "public, max-age=3600, immutable"
PUBLIC_STOREFRONT_CACHE_CONTROL = "public, max-age=60"
_CACHEABLE_METHODS = frozenset({"GET", "HEAD"})


@dataclass(frozen=True)
class CacheablePolicy:
    """The approved cache grant for one registered endpoint.

    ``cache_control`` is the exact header value; ``statuses`` is the closed
    set of response statuses it applies to. Anything else from the same
    endpoint — every error, every unsafe method — stays ``no-store``.
    """

    cache_control: str
    statuses: frozenset[int]


# The two approved grants, named so the composition root and the tests
# share one definition of each policy rather than re-typing header values.
PUBLIC_MEDIA_POLICY = CacheablePolicy(PUBLIC_MEDIA_CACHE_CONTROL, frozenset({200, 304}))
PUBLIC_STOREFRONT_POLICY = CacheablePolicy(PUBLIC_STOREFRONT_CACHE_CONTROL, frozenset({200}))


class NoStoreApiMiddleware:
    """Pure ASGI middleware stamping the approved cache policy.

    ``cacheable_endpoints`` maps each handler whose successful responses
    may be publicly cached to its approved policy. The application factory
    supplies it, so this module needs no knowledge of routers or URL
    shapes, and a route that was never wired here can never become
    cacheable. Endpoint lookup is by object identity (functions hash and
    compare by identity), so a lookalike path, a sibling route, or a
    future route under the same prefix can never satisfy it.
    """

    def __init__(
        self, app: ASGIApp, *, cacheable_endpoints: Mapping[Callable[..., Any], CacheablePolicy]
    ) -> None:
        self.app = app
        self._cacheable_endpoints = dict(cacheable_endpoints)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(_PREFIX):
            await self.app(scope, receive, send)
            return

        cacheable_method = scope["method"] in _CACHEABLE_METHODS

        async def send_with_cache_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                # ``endpoint`` is written into the scope by routing, so it is
                # populated by the time a response starts; an unmatched path
                # has none at all.
                endpoint = scope.get("endpoint")
                policy = (
                    self._cacheable_endpoints.get(endpoint)
                    if cacheable_method and endpoint is not None
                    else None
                )
                cacheable = policy is not None and message["status"] in policy.statuses
                MutableHeaders(scope=message)["Cache-Control"] = (
                    policy.cache_control if cacheable and policy is not None else _NO_STORE
                )
            await send(message)

        await self.app(scope, receive, send_with_cache_policy)
