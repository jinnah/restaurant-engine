"""Global known-Host guard (M2C, ADR-013).

Non-integration: the guard rejects before routing, and the allowed-host
cases hit routes that fail fast (401 without a cookie, or the exempt health
probe) so no database is needed.
"""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

_PLATFORM_LIST = "/api/v1/platform/businesses"  # authenticated route → 401 without a cookie


def _client(**overrides: object) -> TestClient:
    return TestClient(create_app(make_settings(**overrides)))


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
