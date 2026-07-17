"""Public Business resolution and isolation (M2C, ADR-013).

The public surface resolves the Business from the request Host only. These
tests prove the neutral-failure contract and that nothing but the Host can
influence resolution. They run against real PostgreSQL (integration marker
via the security conftest).
"""

from fastapi.testclient import TestClient

from tests.security.conftest import (
    BROWSER_HEADERS,
    CreateBusiness,
    CreateMembership,
    CreateUser,
    login_as,
)

_SITE = "/api/v1/public/site"


def _host(slug_host: str) -> dict[str, str]:
    return {"host": slug_host}


def _get(client: TestClient, host: str, **kwargs: object) -> object:
    return client.get(_SITE, headers=_host(host), **kwargs)  # type: ignore[arg-type]


class TestActiveResolution:
    def test_active_business_returns_only_the_four_public_fields(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business(
            "shalik", name="Shalik", status="active", timezone="America/New_York", currency="USD"
        )
        response = client.get(_SITE, headers=_host("shalik.localhost"))
        assert response.status_code == 200
        assert response.json() == {
            "name": "Shalik",
            "slug": "shalik",
            "timezone": "America/New_York",
            "currency": "USD",
        }
        assert response.headers["cache-control"] == "no-store"

    def test_two_active_businesses_resolve_by_their_own_host(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        # Negative control for the slug predicate: each host returns its own
        # business. A resolver that dropped the slug filter would return an
        # arbitrary row and fail one of these assertions.
        create_business("alpha", name="Alpha", status="active")
        create_business("bravo", name="Bravo", status="active")
        assert client.get(_SITE, headers=_host("alpha.localhost")).json()["slug"] == "alpha"
        assert client.get(_SITE, headers=_host("bravo.localhost")).json()["slug"] == "bravo"


class TestNeutralFailures:
    def _assert_neutral_404(self, response: object) -> None:
        assert response.status_code == 404  # type: ignore[attr-defined]
        body = response.json()  # type: ignore[attr-defined]
        assert set(body) == {"error"}
        assert body["error"]["code"] == "not_found"
        assert body["error"]["message"] == "Not found."
        assert body["error"]["field_errors"] == []
        assert body["error"]["details"] is None
        # No business-state-specific field leaks in.
        assert "status" not in body["error"]
        assert response.headers["cache-control"] == "no-store"  # type: ignore[attr-defined]

    def test_unknown_host_is_neutral_404(self, client: TestClient) -> None:
        self._assert_neutral_404(client.get(_SITE, headers=_host("nope.localhost")))

    def test_non_active_states_are_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        # Negative control for the active-status predicate: none of these
        # resolve. A resolver that dropped the status filter would 200 and
        # leak the business (failing these).
        for state in ("provisioning", "suspended", "closed"):
            create_business(f"biz-{state}", name=state.title(), status=state)
            self._assert_neutral_404(client.get(_SITE, headers=_host(f"biz-{state}.localhost")))

    def test_reserved_label_is_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        # Reserved labels can never be created, but the resolver refuses them
        # regardless (defense in depth).
        self._assert_neutral_404(client.get(_SITE, headers=_host("api.localhost")))
        self._assert_neutral_404(client.get(_SITE, headers=_host("admin.localhost")))
        self._assert_neutral_404(client.get(_SITE, headers=_host("www.localhost")))

    def test_off_apex_host_is_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", name="Shalik", status="active")
        # Right slug, wrong apex → not resolvable.
        self._assert_neutral_404(client.get(_SITE, headers=_host("shalik.evil.example.net")))

    def test_apex_and_deep_subdomain_are_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", name="Shalik", status="active")
        self._assert_neutral_404(client.get(_SITE, headers=_host("localhost")))  # apex
        self._assert_neutral_404(client.get(_SITE, headers=_host("a.shalik.localhost")))  # deep

    def test_malformed_and_ip_hosts_are_neutral_404(self, client: TestClient) -> None:
        self._assert_neutral_404(client.get(_SITE, headers=_host("bad_host")))
        self._assert_neutral_404(client.get(_SITE, headers=_host("127.0.0.1")))
        self._assert_neutral_404(client.get(_SITE, headers=_host("")))  # empty Host

    def test_short_label_is_neutral_404(self, client: TestClient) -> None:
        # A 2-char subdomain passes DNS-label rules but not the slug shape.
        self._assert_neutral_404(client.get(_SITE, headers=_host("ab.localhost")))

    def test_all_failure_modes_are_indistinguishable(self, client: TestClient) -> None:
        # The correlation id legitimately differs per request; everything
        # else in the contract must be identical.
        def _contract(host: str) -> tuple[int, dict[str, object], str]:
            response = client.get(_SITE, headers=_host(host))
            error = dict(response.json()["error"])
            error.pop("correlation_id")
            return response.status_code, error, response.headers["cache-control"]

        contracts = [
            _contract(h)
            for h in ("nope.localhost", "api.localhost", "bad_host", "127.0.0.1", "localhost")
        ]
        assert all(c == contracts[0] for c in contracts)


class TestNothingButHostResolves:
    def test_forwarded_host_cannot_influence_resolution(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", name="Shalik", status="active")
        # Real Host unknown, spoofed X-Forwarded-Host pointing at a real
        # business → still 404.
        assert (
            client.get(
                _SITE,
                headers={"host": "nope.localhost", "X-Forwarded-Host": "shalik.localhost"},
            ).status_code
            == 404
        )
        # Real Host valid, forwarded pointing elsewhere → resolves the real Host.
        assert (
            client.get(
                _SITE,
                headers={"host": "shalik.localhost", "X-Forwarded-Host": "other.localhost"},
            ).json()["slug"]
            == "shalik"
        )

    def test_query_params_and_ids_cannot_select_a_business(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        bid = create_business("shalik", name="Shalik", status="active")
        response = client.get(
            f"{_SITE}?business_id={bid}&__business=shalik&slug=shalik",
            headers=_host("nope.localhost"),
        )
        assert response.status_code == 404

    def test_authenticated_cookie_for_another_business_does_not_influence_resolution(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        bid_b = create_business("bravo", name="Bravo", status="active")
        owner_b = create_user("owner-b@example.com")
        create_membership(bid_b, owner_b, role="owner")
        create_business("alpha", name="Alpha", status="active")
        # Log in as B's owner (sets a session cookie), then request Host A.
        login_as(client, "owner-b@example.com")
        assert client.get(_SITE, headers=_host("alpha.localhost")).json()["slug"] == "alpha"
        # And an unknown host is still 404 despite the valid session.
        assert client.get(_SITE, headers=_host("nope.localhost")).status_code == 404

    def test_platform_admin_state_does_not_influence_resolution(
        self, client: TestClient, create_user: CreateUser, create_business: CreateBusiness
    ) -> None:
        create_user("admin@example.com", is_platform_admin=True)
        create_business("suspended-one", name="Suspended", status="suspended")
        login_as(client, "admin@example.com")
        # A platform admin gets no special public visibility.
        assert client.get(_SITE, headers=_host("suspended-one.localhost")).status_code == 404

    def test_public_endpoint_needs_no_csrf_or_browser_context(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", name="Shalik", status="active")
        # No Origin/Sec-Fetch/CSRF headers at all → still 200 (it is a safe,
        # unauthenticated GET).
        assert client.get(_SITE, headers=_host("shalik.localhost")).status_code == 200


class TestSuspendedMemberRegression:
    def test_suspended_member_read_still_returns_200(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # M2B invariant unchanged: the authenticated member read of a
        # suspended business is 200 with visible status (only the PUBLIC
        # surface hides it).
        bid = create_business("paused", name="Paused", status="suspended")
        owner = create_user("owner@example.com")
        create_membership(bid, owner, role="owner")
        login_as(client, "owner@example.com")
        response = client.get(f"/api/v1/businesses/{bid}", headers=BROWSER_HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "suspended"

    def test_creating_a_reserved_slug_business_is_field_level_422(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        from tests.security.conftest import csrf_headers

        create_user("admin@example.com", is_platform_admin=True)
        csrf = login_as(client, "admin@example.com")
        response = client.post(
            "/api/v1/platform/businesses",
            json={"name": "Reserved", "slug": "admin"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert any(fe["field"] == "body.slug" for fe in body["error"]["field_errors"])
