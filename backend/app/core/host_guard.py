"""Global known-Host guard (M2C, ADR-013).

Coarse routing hardening for ordinary API traffic: a request whose Host is
not a recognized platform host family is rejected with an ADR-008 400 before
it reaches a route. This is **input validation and routing hardening, not
tenant authentication** — a Host header is unauthenticated client input, and
authorization elsewhere relies on the session cookie, CSRF checks,
membership, and route identifiers, never on the Host.

Two exemptions reach the app regardless of Host:

* ``/health/live`` and ``/health/ready`` — the registered probe endpoints
  (an exact set, not a prefix: ``/healthanything`` is NOT exempt);
* **``GET`` and ``HEAD`` under ``/api/v1/public/``** — the host-resolved
  public router owns all of its own Host failures and returns the neutral
  404 contract (never a 400 from here).

The public exemption is a **method-scoped prefix** (ADR-013 amendment,
M3D). It was an exact single path while ``/public/site`` was the only
public route; a templated public path (``/public/media/{asset_id}/
{variant}``) cannot be expressed that way, because this guard reads the
raw ASGI path before routing has matched any parameter. The prefix is
safe because ``/api/v1/public/`` belongs to exactly one router — the
host-resolved public one — while the other unauthenticated surfaces
(``/api/v1/password-resets``, ``/api/v1/invitations``) sit outside it and
stay guarded. Only the safe methods are exempt: the justification for
exempting a public route is that its handler resolves the tenant itself,
which is true only of the read-only routes the public surface serves. An
unsafe method under the prefix matches no public route, so there is no
resolver to own its failure and no neutral contract to honor — it keeps
the guard's 400 from an unrecognized Host. A permanent test proves every
registered public GET/HEAD route (schema-hidden HEAD companions included)
carries ``resolve_public_business`` in its dependency graph.

The Host is read through ``sole_host_header``: zero or multiple Host header
values fail closed here exactly as they do in the public resolver.

Recognized host families:

* the platform base domain apex, and any **direct** subdomain of it
  (covers tenant subdomains and the infrastructure labels api/admin/www);
* in development/test only: ``localhost``, ``127.0.0.1``, ``::1``, and
  ``testserver`` (the TestClient origin).
"""

from fastapi import status
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import ErrorCode, error_response
from app.core.hosts import normalize_host, sole_host_header
from app.core.settings import Settings

# The host-resolved public router's mount point. Every route beneath it
# resolves the Business from the Host itself and renders its own neutral
# 404, so the guard must not pre-empt them with a 400 (ADR-013 amendment).
PUBLIC_PATH_PREFIX = "/api/v1/public/"
# Only safe methods are exempt: an unsafe method under the prefix matches
# no public route, so nothing there owns the neutral-failure contract.
PUBLIC_EXEMPT_METHODS = frozenset({"GET", "HEAD"})
# The registered health endpoints, exactly (see app/api/health.py). A guard
# test asserts this set matches the routes actually mounted, so adding a
# probe without updating the exemption fails loudly.
_EXEMPT_HEALTH_PATHS = frozenset({"/health/live", "/health/ready"})
# Loopback/test hosts permitted only outside production.
_DEV_NAMED_HOSTS = frozenset({"localhost", "testserver"})
_DEV_IP_HOSTS = frozenset({"127.0.0.1", "::1"})


class KnownHostGuardMiddleware:
    """Reject requests to non-exempt routes from unrecognized Hosts."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self._base_labels = settings.platform_base_domain_labels
        self._is_production = settings.is_production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in _EXEMPT_HEALTH_PATHS or self._is_exempt_public(scope, path):
            await self.app(scope, receive, send)
            return

        if self._is_known_host(sole_host_header(scope["headers"])):
            await self.app(scope, receive, send)
            return

        # Correlation id is set by the outer correlation middleware, so the
        # ADR-008 envelope carries it; NoStore (also outer) stamps /api/v1.
        response = error_response(
            Request(scope, receive),
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.HTTP_ERROR,
            "Unrecognized Host header.",
        )
        await response(scope, receive, send)

    @staticmethod
    def _is_exempt_public(scope: Scope, path: str) -> bool:
        """True for a safe-method request to the host-resolved public router."""
        return path.startswith(PUBLIC_PATH_PREFIX) and scope["method"] in PUBLIC_EXEMPT_METHODS

    def _is_known_host(self, raw_host: str | None) -> bool:
        normalized = normalize_host(raw_host)
        if normalized is None:
            return False
        if normalized.is_ip:
            return (not self._is_production) and normalized.hostname in _DEV_IP_HOSTS
        if (not self._is_production) and normalized.hostname in _DEV_NAMED_HOSTS:
            return True
        labels = normalized.labels
        if labels == self._base_labels:  # the apex itself
            return True
        # A direct subdomain: exactly one leading label above the base.
        return len(labels) == len(self._base_labels) + 1 and labels[1:] == self._base_labels
