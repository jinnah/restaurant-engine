"""Tenant isolation matrix v1 (M2B).

Proves the platform-route / member-route separation and existence
non-disclosure for business-scoped access and memberships. The corrected
platform-admin case (approved point 5): a platform admin with no membership
gets 404 from the member route but 200 from the platform route.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

_PLATFORM_ROUTES = "/api/v1/platform/businesses"


def _member_get(client: TestClient, business_id: uuid.UUID | str) -> int:
    return int(client.get(f"/api/v1/businesses/{business_id}").status_code)


def _platform_get(client: TestClient, business_id: uuid.UUID | str) -> int:
    return int(client.get(f"{_PLATFORM_ROUTES}/{business_id}").status_code)


class TestMemberRouteIsolation:
    def test_member_reads_own_business(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        bid = create_business("alpha", status="active")
        owner = create_user("owner-a@example.com")
        create_membership(bid, owner, role="owner")
        login_as(client, "owner-a@example.com")
        response = client.get(f"/api/v1/businesses/{bid}")
        assert response.status_code == 200
        assert response.json()["slug"] == "alpha"

    def test_member_cannot_read_another_tenant(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        bid_a = create_business("alpha")
        bid_b = create_business("bravo")
        owner_a = create_user("owner-a@example.com")
        create_membership(bid_a, owner_a, role="owner")
        login_as(client, "owner-a@example.com")
        # Tenant B is indistinguishable from a nonexistent business.
        assert _member_get(client, bid_b) == 404
        assert _member_get(client, uuid.uuid4()) == 404

    def test_suspended_own_business_still_returns_200_with_status(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        bid = create_business("alpha", status="suspended")
        owner = create_user("owner-a@example.com")
        create_membership(bid, owner, role="owner")
        login_as(client, "owner-a@example.com")
        response = client.get(f"/api/v1/businesses/{bid}")
        assert response.status_code == 200
        assert response.json()["status"] == "suspended"

    def test_unauthenticated_member_route_is_401(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        bid = create_business("alpha")
        assert _member_get(client, bid) == 401


class TestPlatformRouteIsolation:
    def test_non_platform_user_is_403_on_every_platform_route(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        bid = create_business("alpha")
        owner = create_user("owner-a@example.com")
        create_membership(bid, owner, role="owner")
        csrf = login_as(client, "owner-a@example.com")

        # An owner is a member, but not a platform admin → 403 everywhere.
        assert client.get(_PLATFORM_ROUTES).status_code == 403
        assert _platform_get(client, bid) == 403
        assert (
            client.post(
                _PLATFORM_ROUTES,
                json={"name": "X", "slug": "new-slug"},
                headers=csrf_headers(csrf),
            ).status_code
            == 403
        )
        for verb in ("activate", "suspend", "reactivate", "close"):
            assert (
                client.post(
                    f"{_PLATFORM_ROUTES}/{bid}/{verb}", json={}, headers=csrf_headers(csrf)
                ).status_code
                == 403
            )

    def test_platform_admin_can_read_any_business(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        bid = create_business("alpha")
        create_user("admin@example.com", is_platform_admin=True)
        login_as(client, "admin@example.com")
        assert _platform_get(client, bid) == 200

    def test_platform_get_missing_business_is_404(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user("admin@example.com", is_platform_admin=True)
        login_as(client, "admin@example.com")
        assert _platform_get(client, uuid.uuid4()) == 404


class TestPlatformAdminHasNoImplicitMembership:
    """Corrected matrix (approved point 5): the membership-less platform
    admin gets 404 from the member route and 200 from the platform route."""

    def test_platform_admin_member_route_404_platform_route_200(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        bid = create_business("alpha", status="active")
        create_user("admin@example.com", is_platform_admin=True)
        login_as(client, "admin@example.com")
        # No membership row exists for the admin → member route 404.
        assert _member_get(client, bid) == 404
        # Platform capability (the flag) → platform route 200.
        assert _platform_get(client, bid) == 200


class TestMembershipDatabaseIsolation:
    def test_one_membership_per_user_per_business(
        self,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        bid = create_business("alpha")
        user = create_user("u@example.com")
        create_membership(bid, user, role="owner")
        with migrated_engine.begin() as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO memberships (id, business_id, user_id, role)"
                        " VALUES (:id, :bid, :uid, 'manager')"
                    ),
                    {"id": uuid.uuid4(), "bid": bid, "uid": user},
                )
                raised = False
            except Exception:
                raised = True
        assert raised, "duplicate membership must violate the unique constraint"

    def test_membership_to_missing_business_is_rejected(
        self, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        user = create_user("u@example.com")
        with migrated_engine.begin() as connection:
            try:
                connection.execute(
                    text(
                        "INSERT INTO memberships (id, business_id, user_id, role)"
                        " VALUES (:id, :bid, :uid, 'owner')"
                    ),
                    {"id": uuid.uuid4(), "bid": uuid.uuid4(), "uid": user},
                )
                raised = False
            except Exception:
                raised = True
        assert raised, "membership FK to a nonexistent business must be rejected"

    def test_business_with_memberships_cannot_be_deleted(
        self,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        bid = create_business("alpha")
        user = create_user("u@example.com")
        create_membership(bid, user, role="owner")
        with migrated_engine.begin() as connection:
            try:
                connection.execute(text("DELETE FROM businesses WHERE id = :id"), {"id": bid})
                raised = False
            except Exception:
                raised = True
        assert raised, "ON DELETE RESTRICT must block deleting a business with memberships"
