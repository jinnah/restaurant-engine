"""Bounded deterministic platform business pagination (M2B, point 7)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.security.conftest import CreateBusiness, CreateUser, login_as

_ROUTE = "/api/v1/platform/businesses"


def _admin(client: TestClient, create_user: CreateUser) -> None:
    create_user("admin@example.com", is_platform_admin=True)
    login_as(client, "admin@example.com")


class TestPagination:
    def test_defaults(self, client: TestClient, create_user: CreateUser) -> None:
        _admin(client, create_user)
        body = client.get(_ROUTE).json()
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert body["total"] == 0
        assert body["items"] == []

    def test_order_is_created_desc_and_stable(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        # Distinct insertion times → newest first, and the order is
        # identical across requests (deterministic).
        for i in range(5):
            create_business(f"rest-{i}", name=f"R{i}")
        _admin(client, create_user)
        first = [b["slug"] for b in client.get(_ROUTE).json()["items"]]
        second = [b["slug"] for b in client.get(_ROUTE).json()["items"]]
        assert first == second
        assert first == ["rest-4", "rest-3", "rest-2", "rest-1", "rest-0"]

    def test_id_desc_tiebreak_on_equal_created_at(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        # Force a created_at tie in one transaction so only the id DESC
        # tiebreak decides the order (total ordering, approved point 7).
        ids = sorted(uuid.uuid4() for _ in range(3))
        with migrated_engine.begin() as connection:
            for n, bid in enumerate(ids):
                connection.execute(
                    text(
                        "INSERT INTO businesses (id, name, slug, status, created_at,"
                        " updated_at) VALUES (:id, :name, :slug, 'provisioning',"
                        " '2026-07-16T00:00:00+00', '2026-07-16T00:00:00+00')"
                    ),
                    {"id": bid, "name": f"Tie {n}", "slug": f"tie-{n}"},
                )
        _admin(client, create_user)
        returned = [uuid.UUID(b["id"]) for b in client.get(_ROUTE).json()["items"]]
        assert returned == sorted(ids, reverse=True)

    def test_offset_paging_has_no_gap_or_overlap(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        for i in range(5):
            create_business(f"rest-{i}")
        _admin(client, create_user)
        page1 = client.get(f"{_ROUTE}?limit=2&offset=0").json()
        page2 = client.get(f"{_ROUTE}?limit=2&offset=2").json()
        page3 = client.get(f"{_ROUTE}?limit=2&offset=4").json()
        assert page1["total"] == page2["total"] == 5
        ids = (
            [b["id"] for b in page1["items"]]
            + [b["id"] for b in page2["items"]]
            + [b["id"] for b in page3["items"]]
        )
        assert len(ids) == 5
        assert len(set(ids)) == 5  # no overlap; covers every row exactly once

    def test_bounds_are_rejected(self, client: TestClient, create_user: CreateUser) -> None:
        _admin(client, create_user)
        assert client.get(f"{_ROUTE}?limit=0").status_code == 422
        assert client.get(f"{_ROUTE}?limit=101").status_code == 422
        assert client.get(f"{_ROUTE}?offset=-1").status_code == 422

    def test_max_limit_is_accepted(self, client: TestClient, create_user: CreateUser) -> None:
        _admin(client, create_user)
        assert client.get(f"{_ROUTE}?limit=100").status_code == 200
