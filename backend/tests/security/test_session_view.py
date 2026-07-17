"""Enriched auth_session view (M2B): membership projection and sorting.

The projection is composed at the application layer from identity
memberships and business summaries, bound to the caller's own id, sorted
business_name ASC, business_id ASC (approved addendum decision 2).
"""

from fastapi.testclient import TestClient

from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    login_as,
)


class TestSessionMemberships:
    def test_owner_sees_only_their_memberships(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        bid_a = create_business("alpha", name="Alpha", status="active")
        create_business("beta", name="Beta")  # not a member of this one
        owner = create_user("owner@example.com")
        create_membership(bid_a, owner, role="owner")

        login_as(client, "owner@example.com")
        body = client.get("/api/v1/auth/session").json()
        assert [m["business_slug"] for m in body["memberships"]] == ["alpha"]
        membership = body["memberships"][0]
        assert membership["business_id"] == str(bid_a)
        assert membership["business_name"] == "Alpha"
        assert membership["role"] == "owner"
        assert membership["business_status"] == "active"

    def test_memberships_sorted_by_name_then_id(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        bid_z = create_business("zeta", name="Zebra")
        bid_a = create_business("apple", name="Apple")
        bid_m = create_business("mango", name="Mango")
        user = create_user("multi@example.com")
        for bid, role in ((bid_z, "owner"), (bid_a, "manager"), (bid_m, "staff")):
            create_membership(bid, user, role=role)

        login_as(client, "multi@example.com")
        body = client.get("/api/v1/auth/session").json()
        assert [m["business_name"] for m in body["memberships"]] == ["Apple", "Mango", "Zebra"]

    def test_all_statuses_are_included(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # Closed and suspended tenants stay in the projection (decision 9):
        # the API reports true state; hiding is a UI choice.
        bid_closed = create_business("gone", name="Gone", status="closed")
        bid_susp = create_business("paused", name="Paused", status="suspended")
        user = create_user("u@example.com")
        create_membership(bid_closed, user, role="owner")
        create_membership(bid_susp, user, role="manager")

        login_as(client, "u@example.com")
        body = client.get("/api/v1/auth/session").json()
        statuses = {m["business_status"] for m in body["memberships"]}
        assert statuses == {"closed", "suspended"}

    def test_projection_excludes_other_users_memberships(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """Negative control (review finding M-2a): the projection is bound
        to the caller's own id. User B's membership rows exist in the same
        table — if ``list_for_user`` ever lost its ``user_id`` predicate,
        Business B would leak into User A's session and this test fails."""
        bid_a = create_business("alpha", name="Alpha")
        bid_b = create_business("beta", name="Beta")
        user_a = create_user("user-a@example.com")
        user_b = create_user("user-b@example.com")
        create_membership(bid_a, user_a, role="owner")
        create_membership(bid_b, user_b, role="owner")

        login_as(client, "user-a@example.com")
        body = client.get("/api/v1/auth/session").json()
        assert [m["business_slug"] for m in body["memberships"]] == ["alpha"]
        assert all(m["business_id"] != str(bid_b) for m in body["memberships"])

    def test_platform_admin_has_empty_memberships(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user("admin@example.com", is_platform_admin=True)
        login_as(client, "admin@example.com")
        body = client.get("/api/v1/auth/session").json()
        assert body["memberships"] == []
        assert body["user"]["is_platform_admin"] is True

    def test_login_response_stays_lean(self, client: TestClient, create_user: CreateUser) -> None:
        # login keeps the identity-only SessionResponse (no memberships).
        create_user("owner@example.com")
        from tests.security.conftest import login

        body = login(client).json()
        assert "memberships" not in body
        assert set(body) == {"user", "csrf_token"}
