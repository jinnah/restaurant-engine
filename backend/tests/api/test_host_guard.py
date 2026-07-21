"""Global known-Host guard (M2C, ADR-013).

Non-integration: the guard rejects before routing, and the allowed-host
cases hit routes that fail fast (401 without a cookie, or the exempt health
probe) so no database is needed.

Duplicate-Host tests drive the composed ASGI app directly with a hand-built
scope: HTTP test clients normalize or replace the Host header, so genuinely
separate duplicate values can only be exercised at the ASGI layer.
"""

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any

from fastapi.testclient import TestClient

from app.core.host_guard import _EXEMPT_HEALTH_PATHS
from app.main import create_app
from tests.conftest import make_settings

_PLATFORM_LIST = "/api/v1/platform/businesses"  # authenticated route → 401 without a cookie
_PUBLIC_SITE = "/api/v1/public/site"


def _client(**overrides: object) -> TestClient:
    return TestClient(create_app(make_settings(**overrides)))


def _asgi_get(
    path: str, headers: list[tuple[bytes, bytes]]
) -> tuple[int, dict[str, str], dict[str, Any]]:
    """GET ``path`` against the real composed app with raw ASGI headers.

    Returns (status, response headers, decoded JSON body). Bypasses every
    HTTP client so duplicate Host headers reach the app exactly as sent.
    """
    app = create_app(make_settings())
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
    }
    messages: list[MutableMapping[str, Any]] = []

    async def receive() -> MutableMapping[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    response_headers = {
        name.decode("latin-1").lower(): value.decode("latin-1") for name, value in start["headers"]
    }
    return start["status"], response_headers, json.loads(body)


class TestKnownHostGuard:
    def test_testserver_is_allowed_in_test_env(self) -> None:
        # Default TestClient Host is 'testserver'; a no-cookie request reaches
        # the route and gets 401 (not a 400 from the guard).
        client = _client()
        assert client.get(_PLATFORM_LIST).status_code == 401

    def test_direct_subdomain_of_base_is_allowed(self) -> None:
        client = _client()
        response = client.get(_PLATFORM_LIST, headers={"host": "shalik.localhost"})
        assert response.status_code == 401

    def test_unknown_host_is_rejected_with_adr008_400(self) -> None:
        client = _client()
        response = client.get(_PLATFORM_LIST, headers={"host": "evil.example.net"})
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "http_error"
        assert body["error"]["correlation_id"]
        # /api/v1 rejections stay no-store; correlation id is echoed.
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"]

    def test_malformed_host_is_rejected(self) -> None:
        client = _client()
        assert client.get(_PLATFORM_LIST, headers={"host": "bad_host"}).status_code == 400

    def test_ip_literal_host_rejected_in_production_family(self) -> None:
        # An arbitrary IP is not a known host family on a non-exempt route.
        client = _client()
        # 10.0.0.5 is not a dev loopback IP → rejected even in test env.
        assert client.get(_PLATFORM_LIST, headers={"host": "10.0.0.5"}).status_code == 400

    def test_health_is_exempt_from_the_guard(self) -> None:
        client = _client()
        # Arbitrary probe Host must still reach the liveness probe.
        response = client.get("/health/live", headers={"host": "anything.internal"})
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    def test_authenticated_route_is_host_independent_for_authz(self) -> None:
        # A valid tenant-family Host does not authenticate: still 401 with no
        # cookie. Host never confers authorization.
        client = _client()
        assert client.get(_PLATFORM_LIST, headers={"host": "www.localhost"}).status_code == 401


class TestPublicPrefixExemptionIsMethodScoped:
    """GET/HEAD under /api/v1/public/ are exempt; unsafe methods are not.

    (M3D, ADR-013 amendment.) The public router owns its own Host failures
    for the methods it serves; an unsafe method matches no public route, so
    nothing there owns the neutral contract and the guard still answers.
    """

    def test_public_get_from_unrecognized_host_is_the_neutral_404(self) -> None:
        client = _client()
        response = client.get(_PUBLIC_SITE, headers={"host": "evil.example.net"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert response.headers["cache-control"] == "no-store"

    def test_public_unsafe_method_from_unrecognized_host_is_the_guard_400(self) -> None:
        client = _client()
        for request in (client.post, client.put, client.patch, client.delete):
            response = request(_PUBLIC_SITE, headers={"host": "evil.example.net"})
            assert response.status_code == 400, request.__name__
            assert response.json()["error"]["code"] == "http_error"
            assert response.headers["cache-control"] == "no-store"

    def test_public_unsafe_method_from_known_host_reaches_routing(self) -> None:
        # Past the guard, an unsafe method on a GET-only route is a 405 from
        # routing — never a silent success and never the guard's 400.
        client = _client()
        response = client.post(_PUBLIC_SITE, headers={"host": "shalik.localhost"})
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"

    def test_lookalike_public_prefixes_are_not_exempt(self) -> None:
        client = _client()
        for path in ("/api/v1/publicity", "/api/v1/public", "/api/v1/publicx/thing"):
            response = client.get(path, headers={"host": "evil.example.net"})
            assert response.status_code == 400, path
            assert response.json()["error"]["code"] == "http_error"

    def test_other_unauthenticated_routers_remain_guarded(self) -> None:
        # Password reset and invitation redemption are unauthenticated but do
        # NOT sit under /api/v1/public/, so they keep the guard.
        client = _client()
        for path in ("/api/v1/password-resets/redeem", "/api/v1/invitations/accept"):
            response = client.post(path, headers={"host": "evil.example.net"}, json={})
            assert response.status_code == 400, path
            assert response.json()["error"]["code"] == "http_error"


class TestDuplicateHostHeaders:
    """Separate duplicate Host header values fail closed (review R-1)."""

    def test_duplicate_equal_hosts_on_ordinary_route_are_400(self) -> None:
        status, headers, body = _asgi_get(
            _PLATFORM_LIST,
            [(b"host", b"shalik.localhost"), (b"host", b"shalik.localhost")],
        )
        assert status == 400
        assert body["error"]["code"] == "http_error"
        assert body["error"]["correlation_id"]
        assert headers["cache-control"] == "no-store"
        assert headers["x-request-id"] == body["error"]["correlation_id"]

    def test_duplicate_different_hosts_on_ordinary_route_are_400(self) -> None:
        status, _, body = _asgi_get(
            _PLATFORM_LIST,
            [(b"host", b"shalik.localhost"), (b"host", b"evil.net")],
        )
        assert status == 400
        assert body["error"]["code"] == "http_error"

    def test_duplicate_hosts_on_public_site_are_neutral_404(self) -> None:
        for hosts in (
            [(b"host", b"shalik.localhost"), (b"host", b"shalik.localhost")],
            [(b"host", b"shalik.localhost"), (b"host", b"other.localhost")],
        ):
            status, headers, body = _asgi_get(_PUBLIC_SITE, hosts)
            assert status == 404
            assert body["error"]["code"] == "not_found"
            assert body["error"]["message"] == "Not found."
            assert headers["cache-control"] == "no-store"

    def test_duplicate_hosts_with_forwarded_host_still_fail_closed(self) -> None:
        headers = [
            (b"host", b"shalik.localhost"),
            (b"host", b"shalik.localhost"),
            (b"x-forwarded-host", b"shalik.localhost"),
            (b"forwarded", b"host=shalik.localhost"),
        ]
        status, _, _body = _asgi_get(_PLATFORM_LIST, headers)
        assert status == 400
        status, _, _body = _asgi_get(_PUBLIC_SITE, headers)
        assert status == 404

    def test_missing_host_fails_closed_on_both_surfaces(self) -> None:
        status, _, _ = _asgi_get(_PLATFORM_LIST, [(b"accept", b"*/*")])
        assert status == 400
        status, _, body = _asgi_get(_PUBLIC_SITE, [(b"accept", b"*/*")])
        assert status == 404
        assert body["error"]["code"] == "not_found"

    def test_single_valid_host_still_works(self) -> None:
        # One Host → passes the guard → the route itself answers (401: no
        # session cookie), proving extraction does not break the normal path.
        status, _, body = _asgi_get(_PLATFORM_LIST, [(b"host", b"shalik.localhost")])
        assert status == 401
        assert body["error"]["code"] == "authentication_required"


class TestHealthExemptionIsExact:
    """The guard exempts exactly the registered health routes (review R-2)."""

    def test_exempt_set_matches_registered_health_routes(self) -> None:
        # Derived from the OpenAPI schema (every health route is
        # schema-visible per ADR-009): adding a probe without updating the
        # guard's exemption set fails here.
        spec = create_app(make_settings()).openapi()
        registered = {path for path in spec["paths"] if path.startswith("/health")}
        assert registered == set(_EXEMPT_HEALTH_PATHS)

    def test_health_ready_reachable_with_unrecognized_host(self) -> None:
        client = _client()
        response = client.get("/health/ready", headers={"host": "probe.internal"})
        # Reaches the probe (200 up / 503 down) — never the guard's 400.
        assert response.status_code in (200, 503)

    def test_lookalike_health_paths_are_not_exempt(self) -> None:
        client = _client()
        for path in ("/healthevil", "/healthcheck", "/healthy", "/health/live/extra"):
            response = client.get(path, headers={"host": "evil.example.net"})
            assert response.status_code == 400, path
            assert response.json()["error"]["code"] == "http_error"

    def test_query_string_does_not_affect_exemption(self) -> None:
        client = _client()
        response = client.get("/health/live?probe=1", headers={"host": "evil.example.net"})
        assert response.status_code == 200
