"""Enriched auth_session view (M2B): membership projection and sorting.

The projection is composed at the application layer from identity
memberships and tenant summaries, bound to the caller's own id, sorted
restaurant_name ASC, restaurant_id ASC (approved addendum decision 2).
"""

from fastapi.testclient import TestClient

from tests.security.conftest import (
    CreateMembership,
    CreateRestaurant,
    CreateUser,
    login_as,
)


class TestSessionMemberships:
    def test_owner_sees_only_their_memberships(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_restaurant: CreateRestaurant,
        create_membership: CreateMembership,
    ) -> None:
        rid_a = create_restaurant("alpha", name="Alpha", status="active")
        create_restaurant("beta", name="Beta")  # not a member of this one
        owner = create_user("owner@example.com")
        create_membership(rid_a, owner, role="owner")

        login_as(client, "owner@example.com")
        body = client.get("/api/v1/auth/session").json()
        assert [m["restaurant_slug"] for m in body["memberships"]] == ["alpha"]
        membership = body["memberships"][0]
        assert membership["restaurant_id"] == str(rid_a)
        assert membership["restaurant_name"] == "Alpha"
        assert membership["role"] == "owner"
        assert membership["restaurant_status"] == "active"

    def test_memberships_sorted_by_name_then_id(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_restaurant: CreateRestaurant,
        create_membership: CreateMembership,
    ) -> None:
        rid_z = create_restaurant("zeta", name="Zebra")
        rid_a = create_restaurant("apple", name="Apple")
        rid_m = create_restaurant("mango", name="Mango")
        user = create_user("multi@example.com")
        for rid, role in ((rid_z, "owner"), (rid_a, "manager"), (rid_m, "staff")):
            create_membership(rid, user, role=role)

        login_as(client, "multi@example.com")
        body = client.get("/api/v1/auth/session").json()
        assert [m["restaurant_name"] for m in body["memberships"]] == ["Apple", "Mango", "Zebra"]

    def test_all_statuses_are_included(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_restaurant: CreateRestaurant,
        create_membership: CreateMembership,
    ) -> None:
        # Closed and suspended tenants stay in the projection (decision 9):
        # the API reports true state; hiding is a UI choice.
        rid_closed = create_restaurant("gone", name="Gone", status="closed")
        rid_susp = create_restaurant("paused", name="Paused", status="suspended")
        user = create_user("u@example.com")
        create_membership(rid_closed, user, role="owner")
        create_membership(rid_susp, user, role="manager")

        login_as(client, "u@example.com")
        body = client.get("/api/v1/auth/session").json()
        statuses = {m["restaurant_status"] for m in body["memberships"]}
        assert statuses == {"closed", "suspended"}

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
