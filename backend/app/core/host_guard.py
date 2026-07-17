"""Global known-Host guard (M2C, ADR-013).

Coarse routing hardening for ordinary API traffic: a request whose Host is
not a recognized platform host family is rejected with an ADR-008 400 before
it reaches a route. This is **input validation and routing hardening, not
tenant authentication** — a Host header is unauthenticated client input, and
authorization elsewhere relies on the session cookie, CSRF checks,
membership, and route identifiers, never on the Host.

Two paths are exempt and reach the app regardless of Host:

* ``/health/*`` — process/orchestration probes use arbitrary Hosts;
* ``GET /api/v1/public/site`` — the public resolver owns all of its own Host
  failures and returns the neutral 404 contract (never a 400 from here).

Recognized host families:

* the platform base domain apex, and any **direct** subdomain of it
  (covers tenant subdomains and the infrastructure labels api/admin/www);
* in development/test only: ``localhost``, ``127.0.0.1``, ``::1``, and
  ``testserver`` (the TestClient origin).
"""

from fastapi import status
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import ErrorCode, error_response
from app.core.hosts import normalize_host
from app.core.settings import Settings

_PUBLIC_SITE_PATH = "/api/v1/public/site"
_HEALTH_PREFIX = "/health"
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
        if path == _PUBLIC_SITE_PATH or path.startswith(_HEALTH_PREFIX):
            await self.app(scope, receive, send)
            return

        if self._is_known_host(Headers(scope=scope).get("host")):
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
