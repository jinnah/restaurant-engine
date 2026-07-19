"""Catalog core behavior, authorization, and tenant isolation (M3A, ADR-017).

Extends the permanent isolation matrix (docs/04) to menu categories,
items, and dietary tags, and proves the service rules: dense normalized
positions, exact-set reorders, the featured policy (R1), name uniqueness
(R6), lifecycle gating (D8), empty-only category deletion (D7), separate
available/hidden states, fail-closed dietary reads (D6), and audit
emission inside the mutation transaction.

Bulk policy-limit fixtures are seeded with set-based SQL (docs/06 advice:
direct policy evidence over hundreds of slow HTTP calls).
"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.domains.catalog import policies
from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

OWNER = "owner@example.com"
MANAGER = "manager@example.com"
STAFF = "staff@example.com"
INTRUDER = "intruder-owner@example.com"
PLATFORM_ADMIN = "admin@example.com"


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/catalog"


def _create_category(
    client: TestClient,
    csrf: str,
    business_id: uuid.UUID,
    name: str = "Curries",
    **extra: Any,
) -> dict[str, Any]:
    response = client.post(
        f"{_base(business_id)}/categories",
        json={"name": name, **extra},
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _create_item(
    client: TestClient,
    csrf: str,
    business_id: uuid.UUID,
    category_id: str,
    name: str = "Samosa",
    price_minor: int = 350,
    **extra: Any,
) -> dict[str, Any]:
    response = client.post(
        f"{_base(business_id)}/categories/{category_id}/items",
        json={"name": name, "price_minor": price_minor, **extra},
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _menu(client: TestClient, business_id: uuid.UUID) -> dict[str, Any]:
    response = client.get(f"{_base(business_id)}/menu")
    assert response.status_code == 200, response.text
    return dict(response.json())


def _error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def _audit_rows(
    engine: Engine, business_id: uuid.UUID, action: str | None = None
) -> list[dict[str, Any]]:
    query = (
        "SELECT action, actor_user_id, business_id, target_type, target_id, details"
        " FROM audit_events WHERE business_id = :bid"
    )
    params: dict[str, Any] = {"bid": business_id}
    if action is not None:
        query += " AND action = :action"
        params["action"] = action
    query += " ORDER BY id"
    with engine.begin() as connection:
        rows = connection.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]


def _audit_count(engine: Engine) -> int:
    with engine.begin() as connection:
        return int(connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one())


class TestCategoryCrud:
    def test_create_normalizes_and_appends_dense_positions(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        first = _create_category(client, csrf, business, name="  Rice   Bowls ")
        second = _create_category(client, csrf, business, name="Curries", description="   ")
        assert first["name"] == "Rice Bowls"
        assert first["position"] == 0
        assert first["is_visible"] is True
        assert second["position"] == 1
        assert second["description"] is None

    def test_duplicate_name_is_rejected_case_insensitively(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        _create_category(client, csrf, business, name="Drinks")
        response = client.post(
            f"{_base(business)}/categories",
            json={"name": "drinks"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert _error_code(response) == "conflict"

    def test_update_changes_only_supplied_fields(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business, description="Original")
        response = client.patch(
            f"{_base(business)}/categories/{category['id']}",
            json={"is_visible": False},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_visible"] is False
        assert body["name"] == category["name"]
        assert body["description"] == "Original"
        events = _audit_rows(migrated_engine, business, "catalog.category_updated")
        assert len(events) == 1
        assert events[0]["details"]["changed_fields"] == "is_visible"

    def test_noop_update_records_no_audit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        response = client.patch(
            f"{_base(business)}/categories/{category['id']}",
            json={"name": category["name"]},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert _audit_rows(migrated_engine, business, "catalog.category_updated") == []

    def test_rename_collision_is_rejected(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        _create_category(client, csrf, business, name="Drinks")
        other = _create_category(client, csrf, business, name="Sweets")
        response = client.patch(
            f"{_base(business)}/categories/{other['id']}",
            json={"name": "DRINKS"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409

    def test_delete_requires_empty_and_normalizes_positions(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        first = _create_category(client, csrf, business, name="First")
        second = _create_category(client, csrf, business, name="Second")
        third = _create_category(client, csrf, business, name="Third")
        item = _create_item(client, csrf, business, second["id"])

        blocked = client.delete(
            f"{_base(business)}/categories/{second['id']}", headers=csrf_headers(csrf)
        )
        assert blocked.status_code == 409
        assert _error_code(blocked) == "conflict"

        deleted_item = client.delete(
            f"{_base(business)}/items/{item['id']}", headers=csrf_headers(csrf)
        )
        assert deleted_item.status_code == 200
        response = client.delete(
            f"{_base(business)}/categories/{second['id']}", headers=csrf_headers(csrf)
        )
        assert response.status_code == 200
        assert response.json() == {"status": "deleted"}

        menu = _menu(client, business)
        names_positions = [(c["name"], c["position"]) for c in menu["categories"]]
        assert names_positions == [(first["name"], 0), (third["name"], 1)]

    def test_unknown_category_is_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        response = client.patch(
            f"{_base(business)}/categories/{uuid.uuid4()}",
            json={"name": "X"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 404


class TestReorders:
    def test_category_reorder_is_full_set_atomic_and_idempotent(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        a = _create_category(client, csrf, business, name="A")
        b = _create_category(client, csrf, business, name="B")
        c = _create_category(client, csrf, business, name="C")
        new_order = [c["id"], a["id"], b["id"]]
        response = client.post(
            f"{_base(business)}/categories/reorder",
            json={"ordered_category_ids": new_order},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        ordered = [cat["id"] for cat in response.json()["categories"]]
        assert ordered == new_order
        positions = [cat["position"] for cat in response.json()["categories"]]
        assert positions == [0, 1, 2]

        # Repeating the identical reorder is a no-op success.
        again = client.post(
            f"{_base(business)}/categories/reorder",
            json={"ordered_category_ids": new_order},
            headers=csrf_headers(csrf),
        )
        assert again.status_code == 200
        assert [cat["id"] for cat in again.json()["categories"]] == new_order
        events = _audit_rows(migrated_engine, business, "catalog.categories_reordered")
        assert len(events) == 2
        assert events[0]["details"] == {"count": 3}

    def test_category_reorder_rejects_inexact_sets(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        a = _create_category(client, csrf, business, name="A")
        _create_category(client, csrf, business, name="B")
        for bad_set in (
            [a["id"]],  # missing one
            [a["id"], str(uuid.uuid4())],  # foreign id substituted
        ):
            response = client.post(
                f"{_base(business)}/categories/reorder",
                json={"ordered_category_ids": bad_set},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 409
            assert _error_code(response) == "conflict"

    def test_item_reorder_within_category(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        one = _create_item(client, csrf, business, category["id"], name="One")
        two = _create_item(client, csrf, business, category["id"], name="Two")
        response = client.post(
            f"{_base(business)}/items/reorder",
            json={"category_id": category["id"], "ordered_item_ids": [two["id"], one["id"]]},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        items = response.json()["categories"][0]["items"]
        assert [item["id"] for item in items] == [two["id"], one["id"]]
        assert [item["position"] for item in items] == [0, 1]

        mismatch = client.post(
            f"{_base(business)}/items/reorder",
            json={"category_id": category["id"], "ordered_item_ids": [two["id"]]},
            headers=csrf_headers(csrf),
        )
        assert mismatch.status_code == 409


class TestItems:
    def test_create_read_update_delete(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        item = _create_item(
            client,
            csrf,
            business,
            category["id"],
            name="  Chicken   Biryani ",
            price_minor=1450,
            dietary_tags=["Halal"],
        )
        assert item["name"] == "Chicken Biryani"
        assert item["price_minor"] == 1450
        assert item["dietary_tags"] == ["halal"]
        assert item["position"] == 0
        assert item["is_available"] is True
        assert item["is_hidden"] is False
        assert item["is_featured"] is False

        read = client.get(f"{_base(business)}/items/{item['id']}")
        assert read.status_code == 200
        assert read.json()["name"] == "Chicken Biryani"

        updated = client.patch(
            f"{_base(business)}/items/{item['id']}",
            json={"price_minor": 1550, "dietary_tags": ["halal", "vegetarian"]},
            headers=csrf_headers(csrf),
        )
        assert updated.status_code == 200
        assert updated.json()["price_minor"] == 1550
        assert updated.json()["dietary_tags"] == ["halal", "vegetarian"]
        events = _audit_rows(migrated_engine, business, "catalog.item_updated")
        assert len(events) == 1
        details = events[0]["details"]
        assert details["changed_fields"] == "dietary_tags,price_minor"
        assert details["price_minor_old"] == 1450
        assert details["price_minor_new"] == 1550

        deleted = client.delete(f"{_base(business)}/items/{item['id']}", headers=csrf_headers(csrf))
        assert deleted.status_code == 200
        with migrated_engine.begin() as connection:
            tags_left = connection.execute(
                text("SELECT count(*) FROM menu_item_dietary_tags WHERE item_id = :iid"),
                {"iid": item["id"]},
            ).scalar_one()
        assert tags_left == 0, "tags must cascade with the item"
        assert client.get(f"{_base(business)}/items/{item['id']}").status_code == 404

    def test_duplicate_names_per_category_only(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        curries = _create_category(client, csrf, business, name="Curries")
        sweets = _create_category(client, csrf, business, name="Sweets")
        _create_item(client, csrf, business, curries["id"], name="Special")
        duplicate = client.post(
            f"{_base(business)}/categories/{curries['id']}/items",
            json={"name": "SPECIAL", "price_minor": 100},
            headers=csrf_headers(csrf),
        )
        assert duplicate.status_code == 409
        # Same normalized name in a different category is allowed (R6).
        _create_item(client, csrf, business, sweets["id"], name="Special")

    def test_hidden_and_available_are_independent_and_featured_survives_hiding(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        item = _create_item(client, csrf, business, category["id"])

        featured = client.patch(
            f"{_base(business)}/items/{item['id']}",
            json={"is_featured": True},
            headers=csrf_headers(csrf),
        )
        assert featured.json()["is_featured"] is True

        hidden = client.patch(
            f"{_base(business)}/items/{item['id']}",
            json={"is_hidden": True},
            headers=csrf_headers(csrf),
        )
        body = hidden.json()
        assert body["is_hidden"] is True
        assert body["is_available"] is True, "hiding must not touch availability"
        assert body["is_featured"] is True, "hiding must not clear the featured flag (R1)"

        sold_out = client.post(
            f"{_base(business)}/items/{item['id']}/availability",
            json={"is_available": False},
            headers=csrf_headers(csrf),
        )
        body = sold_out.json()
        assert body["is_available"] is False
        assert body["is_hidden"] is True, "availability must not touch hidden"
        assert body["is_featured"] is True, "sold-out items may remain featured (R1)"

    def test_move_between_categories(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        source = _create_category(client, csrf, business, name="Source")
        destination = _create_category(client, csrf, business, name="Destination")
        moving = _create_item(client, csrf, business, source["id"], name="Mover")
        staying = _create_item(client, csrf, business, source["id"], name="Stayer")
        existing = _create_item(client, csrf, business, destination["id"], name="Resident")

        response = client.patch(
            f"{_base(business)}/items/{moving['id']}",
            json={"category_id": destination["id"]},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["category_id"] == destination["id"]
        assert body["position"] == 1, "moved item appends at the destination's end"

        menu = _menu(client, business)
        by_name = {c["name"]: c for c in menu["categories"]}
        assert [(i["id"], i["position"]) for i in by_name["Source"]["items"]] == [
            (staying["id"], 0)
        ], "source positions renormalize after the move"
        assert [i["id"] for i in by_name["Destination"]["items"]] == [
            existing["id"],
            moving["id"],
        ]
        events = _audit_rows(migrated_engine, business, "catalog.item_updated")
        assert events[-1]["details"]["changed_fields"] == "category_id"
        assert events[-1]["details"]["category_id"] == destination["id"]

    def test_move_name_collision_and_unknown_destination(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        source = _create_category(client, csrf, business, name="Source")
        destination = _create_category(client, csrf, business, name="Destination")
        item = _create_item(client, csrf, business, source["id"], name="Special")
        _create_item(client, csrf, business, destination["id"], name="special")

        collision = client.patch(
            f"{_base(business)}/items/{item['id']}",
            json={"category_id": destination["id"]},
            headers=csrf_headers(csrf),
        )
        assert collision.status_code == 409

        unknown = client.patch(
            f"{_base(business)}/items/{item['id']}",
            json={"category_id": str(uuid.uuid4())},
            headers=csrf_headers(csrf),
        )
        assert unknown.status_code == 404


class TestAvailabilityCommand:
    def test_toggle_audits_and_is_idempotent(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        item = _create_item(client, csrf, business, category["id"])

        response = client.post(
            f"{_base(business)}/items/{item['id']}/availability",
            json={"is_available": False},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert response.json()["is_available"] is False
        events = _audit_rows(migrated_engine, business, "catalog.item_availability_changed")
        assert len(events) == 1
        assert events[0]["details"] == {"availability": "sold_out"}

        # Same value again: success, no state change, no new audit event.
        again = client.post(
            f"{_base(business)}/items/{item['id']}/availability",
            json={"is_available": False},
            headers=csrf_headers(csrf),
        )
        assert again.status_code == 200
        assert len(_audit_rows(migrated_engine, business, "catalog.item_availability_changed")) == 1

    def test_staff_can_toggle_availability(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        create_membership(business, create_user(STAFF), role="staff")
        owner_csrf = login_as(client, OWNER)
        category = _create_category(client, owner_csrf, business)
        item = _create_item(client, owner_csrf, business, category["id"])

        staff_csrf = login_as(client, STAFF)
        response = client.post(
            f"{_base(business)}/items/{item['id']}/availability",
            json={"is_available": False},
            headers=csrf_headers(staff_csrf),
        )
        assert response.status_code == 200
        assert response.json()["is_available"] is False


class TestPriceBound:
    """F1 ruling: 0 <= price_minor <= 10,000,000, enforced at 422 by the
    schemas, by the named DB CHECK, and faithfully retained by audit."""

    def test_exact_maximum_accepted_and_retained_in_audit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        item = _create_item(
            client, csrf, business, category["id"], name="Banquet", price_minor=1000
        )
        updated = client.patch(
            f"{_base(business)}/items/{item['id']}",
            json={"price_minor": policies.MAX_PRICE_MINOR},
            headers=csrf_headers(csrf),
        )
        assert updated.status_code == 200
        assert updated.json()["price_minor"] == 10_000_000

        # The business audit trail (real read API, typed projection) must
        # retain the exact maximum — never silently drop a valid price.
        trail = client.get(f"/api/v1/businesses/{business}/audit-events")
        assert trail.status_code == 200
        price_events = [
            event for event in trail.json()["items"] if event["action"] == "catalog.item_updated"
        ]
        assert price_events, "the price change must be audited"
        details = price_events[0]["details"]
        assert details["price_minor_old"] == 1000
        assert details["price_minor_new"] == 10_000_000

    def test_above_maximum_rejected_safely_with_no_side_effects(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        item = _create_item(client, csrf, business, category["id"], name="Samosa", price_minor=350)
        before = _audit_count(migrated_engine)

        over_create = client.post(
            f"{_base(business)}/categories/{category['id']}/items",
            json={"name": "Too Expensive", "price_minor": policies.MAX_PRICE_MINOR + 1},
            headers=csrf_headers(csrf),
        )
        assert over_create.status_code == 422
        assert _error_code(over_create) == "validation_error"

        over_update = client.patch(
            f"{_base(business)}/items/{item['id']}",
            json={"price_minor": policies.MAX_PRICE_MINOR + 1},
            headers=csrf_headers(csrf),
        )
        assert over_update.status_code == 422
        assert _error_code(over_update) == "validation_error"

        assert _audit_count(migrated_engine) == before, (
            "rejected price mutations must not create audit events"
        )
        unchanged = client.get(f"{_base(business)}/items/{item['id']}")
        assert unchanged.json()["price_minor"] == 350


class TestFeaturedPolicy:
    def test_limit_is_six_per_business_hidden_included(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        items = [
            _create_item(client, csrf, business, category["id"], name=f"Item {n}")
            for n in range(policies.MAX_FEATURED_ITEMS + 1)
        ]
        for item in items[: policies.MAX_FEATURED_ITEMS]:
            response = client.patch(
                f"{_base(business)}/items/{item['id']}",
                json={"is_featured": True},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200

        # One featured item is hidden; it still counts toward the limit.
        client.patch(
            f"{_base(business)}/items/{items[0]['id']}",
            json={"is_hidden": True},
            headers=csrf_headers(csrf),
        )

        overflow = client.patch(
            f"{_base(business)}/items/{items[-1]['id']}",
            json={"is_featured": True},
            headers=csrf_headers(csrf),
        )
        assert overflow.status_code == 409
        envelope = overflow.json()["error"]
        assert envelope["code"] == "conflict"
        assert envelope["details"] == {"limit": policies.MAX_FEATURED_ITEMS}

        # Re-featuring an already-featured item at the limit is a no-op 200.
        noop = client.patch(
            f"{_base(business)}/items/{items[1]['id']}",
            json={"is_featured": True},
            headers=csrf_headers(csrf),
        )
        assert noop.status_code == 200

        # Unfeaturing frees a slot.
        client.patch(
            f"{_base(business)}/items/{items[1]['id']}",
            json={"is_featured": False},
            headers=csrf_headers(csrf),
        )
        freed = client.patch(
            f"{_base(business)}/items/{items[-1]['id']}",
            json={"is_featured": True},
            headers=csrf_headers(csrf),
        )
        assert freed.status_code == 200


class TestPolicyLimits:
    """Count limits enforced under the business lock; fixtures seeded with
    set-based SQL, not hundreds of HTTP calls."""

    def test_category_limit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) SELECT gen_random_uuid(), :bid, 'bulk-cat-' || n, n,"
                    " true FROM generate_series(0, :top) AS n"
                ),
                {"bid": business, "top": policies.MAX_CATEGORIES_PER_BUSINESS - 1},
            )
        response = client.post(
            f"{_base(business)}/categories",
            json={"name": "One Too Many"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {
            "limit": policies.MAX_CATEGORIES_PER_BUSINESS
        }

    def test_items_per_category_limit_blocks_create_and_move(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        full = _create_category(client, csrf, business, name="Full")
        other = _create_category(client, csrf, business, name="Other")
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " SELECT gen_random_uuid(), :bid, :cid, 'bulk-item-' || n, 500, n,"
                    " true, false, false FROM generate_series(0, :top) AS n"
                ),
                {"bid": business, "cid": full["id"], "top": policies.MAX_ITEMS_PER_CATEGORY - 1},
            )
        create = client.post(
            f"{_base(business)}/categories/{full['id']}/items",
            json={"name": "Overflow", "price_minor": 100},
            headers=csrf_headers(csrf),
        )
        assert create.status_code == 409
        assert create.json()["error"]["details"] == {"limit": policies.MAX_ITEMS_PER_CATEGORY}

        mover = _create_item(client, csrf, business, other["id"], name="Mover")
        move = client.patch(
            f"{_base(business)}/items/{mover['id']}",
            json={"category_id": full["id"]},
            headers=csrf_headers(csrf),
        )
        assert move.status_code == 409

    def test_items_per_business_limit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        target = _create_category(client, csrf, business, name="Target")
        per_category = policies.MAX_ITEMS_PER_CATEGORY
        bulk_categories = policies.MAX_ITEMS_PER_BUSINESS // per_category
        with migrated_engine.begin() as connection:
            for index in range(bulk_categories):
                category_id = connection.execute(
                    text(
                        "INSERT INTO menu_categories (id, business_id, name, position,"
                        " is_visible) VALUES (gen_random_uuid(), :bid, :name, :pos, true)"
                        " RETURNING id"
                    ),
                    {"bid": business, "name": f"bulk-{index}", "pos": index + 1},
                ).scalar_one()
                connection.execute(
                    text(
                        "INSERT INTO menu_items (id, business_id, category_id, name,"
                        " price_minor, position, is_available, is_hidden, is_featured)"
                        " SELECT gen_random_uuid(), :bid, :cid, 'bulk-' || :prefix || n,"
                        " 500, n, true, false, false FROM generate_series(0, :top) AS n"
                    ),
                    {
                        "bid": business,
                        "cid": category_id,
                        "prefix": str(index) + "-",
                        "top": per_category - 1,
                    },
                )
        response = client.post(
            f"{_base(business)}/categories/{target['id']}/items",
            json={"name": "Overflow", "price_minor": 100},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {"limit": policies.MAX_ITEMS_PER_BUSINESS}


class TestLifecycleGating:
    def test_suspended_business_remains_editable(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business(status="active")
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        _create_category(client, csrf, business, name="Before")
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'suspended' WHERE id = :bid"),
                {"bid": business},
            )
        _create_category(client, csrf, business, name="While Suspended")

    def test_closed_business_is_immutable_but_readable(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business(status="active")
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        item = _create_item(client, csrf, business, category["id"])
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'closed' WHERE id = :bid"),
                {"bid": business},
            )

        for attempt in (
            client.post(
                f"{_base(business)}/categories",
                json={"name": "New"},
                headers=csrf_headers(csrf),
            ),
            client.patch(
                f"{_base(business)}/items/{item['id']}",
                json={"price_minor": 999},
                headers=csrf_headers(csrf),
            ),
            client.post(
                f"{_base(business)}/items/{item['id']}/availability",
                json={"is_available": False},
                headers=csrf_headers(csrf),
            ),
            client.delete(
                f"{_base(business)}/categories/{category['id']}",
                headers=csrf_headers(csrf),
            ),
        ):
            assert attempt.status_code == 409
            assert _error_code(attempt) == "invalid_state"

        # Reads still work: closure retains data (docs/03).
        assert client.get(f"{_base(business)}/menu").status_code == 200
        assert client.get(f"{_base(business)}/items/{item['id']}").status_code == 200


class TestDietaryFailClosedReads:
    def test_unregistered_stored_tag_is_never_surfaced(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        category = _create_category(client, csrf, business)
        item = _create_item(client, csrf, business, category["id"], dietary_tags=["halal"])
        # Simulate drift: a lowercase-canonical but unregistered tag.
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO menu_item_dietary_tags (id, business_id, item_id, tag)"
                    " VALUES (gen_random_uuid(), :bid, :iid, 'spicy')"
                ),
                {"bid": business, "iid": item["id"]},
            )
        read = client.get(f"{_base(business)}/items/{item['id']}")
        assert read.json()["dietary_tags"] == ["halal"]
        menu = _menu(client, business)
        assert menu["categories"][0]["items"][0]["dietary_tags"] == ["halal"]


class TestAuditAtomicity:
    def test_commit_time_constraint_failure_rolls_back_mutation_and_audit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        """The DEFERRED position unique fires at commit — after the audit
        event was recorded — so a commit failure must remove both."""
        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        # A non-dense seeded position: the next API create computes
        # position = count = 1, colliding at commit time.
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Seeded', 1, true)"
                ),
                {"bid": business},
            )
        response = client.post(
            f"{_base(business)}/categories",
            json={"name": "Doomed"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert _error_code(response) == "conflict"
        with migrated_engine.begin() as connection:
            rows = connection.execute(
                text("SELECT count(*) FROM menu_categories WHERE name = 'Doomed'")
            ).scalar_one()
        assert rows == 0, "the failed mutation must not persist"
        assert _audit_rows(migrated_engine, business, "catalog.category_created") == [], (
            "the audit event must roll back with its mutation"
        )

    def test_name_race_integrity_error_converts_to_conflict(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        monkeypatch: Any,
    ) -> None:
        """With the friendly precheck disabled (simulating the race window),
        the expression index converts to the same safe 409 (R6)."""
        from app.domains.catalog import repository as catalog_repository

        business = create_business()
        create_membership(business, create_user(OWNER))
        csrf = login_as(client, OWNER)
        _create_category(client, csrf, business, name="Drinks")
        monkeypatch.setattr(catalog_repository, "category_name_exists", lambda *a, **k: False)
        response = client.post(
            f"{_base(business)}/categories",
            json={"name": "DRINKS"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert _error_code(response) == "conflict"


class TestAuthorizationMatrix:
    def test_anonymous_requests_are_rejected(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        business = create_business()
        assert client.get(f"{_base(business)}/menu").status_code == 401
        assert client.post(f"{_base(business)}/categories", json={"name": "X"}).status_code == 401

    def test_unsafe_requests_require_the_csrf_token(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        login_as(client, OWNER)
        before = _audit_count(migrated_engine)
        response = client.post(
            f"{_base(business)}/categories",
            json={"name": "X"},
            headers={"Origin": "http://testserver"},  # browser context, no token
        )
        assert response.status_code == 403
        assert _error_code(response) == "csrf_rejected"
        assert _audit_count(migrated_engine) == before
        assert _menu_is_empty(client, business)

    def test_staff_cannot_write_but_can_read_and_toggle(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        create_membership(business, create_user(STAFF), role="staff")
        owner_csrf = login_as(client, OWNER)
        category = _create_category(client, owner_csrf, business)
        item = _create_item(client, owner_csrf, business, category["id"])

        staff_csrf = login_as(client, STAFF)
        before = _audit_count(migrated_engine)
        denied = [
            client.post(
                f"{_base(business)}/categories",
                json={"name": "Staff Cat"},
                headers=csrf_headers(staff_csrf),
            ),
            client.patch(
                f"{_base(business)}/categories/{category['id']}",
                json={"name": "Renamed"},
                headers=csrf_headers(staff_csrf),
            ),
            client.delete(
                f"{_base(business)}/items/{item['id']}", headers=csrf_headers(staff_csrf)
            ),
            client.patch(
                f"{_base(business)}/items/{item['id']}",
                json={"price_minor": 1},
                headers=csrf_headers(staff_csrf),
            ),
            client.post(
                f"{_base(business)}/categories/reorder",
                json={"ordered_category_ids": [category["id"]]},
                headers=csrf_headers(staff_csrf),
            ),
            client.post(
                f"{_base(business)}/items/reorder",
                json={"category_id": category["id"], "ordered_item_ids": [item["id"]]},
                headers=csrf_headers(staff_csrf),
            ),
        ]
        for response in denied:
            assert response.status_code == 403
            assert _error_code(response) == "permission_denied"
        assert _audit_count(migrated_engine) == before, "rejected writes must not audit"

        assert client.get(f"{_base(business)}/menu").status_code == 200
        # The one staff-reachable command (D4).
        toggle = client.post(
            f"{_base(business)}/items/{item['id']}/availability",
            json={"is_available": False},
            headers=csrf_headers(staff_csrf),
        )
        assert toggle.status_code == 200

    def test_manager_holds_general_catalog_write(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(MANAGER), role="manager")
        csrf = login_as(client, MANAGER)
        _create_category(client, csrf, business, name="Manager Made")

    def test_platform_admin_without_membership_gets_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(OWNER))
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        csrf = login_as(client, PLATFORM_ADMIN)
        assert client.get(f"{_base(business)}/menu").status_code == 404
        response = client.post(
            f"{_base(business)}/categories",
            json={"name": "Admin Cat"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 404

    def test_cross_tenant_isolation(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_a = create_business(slug="tenant-a", name="Tenant A")
        business_b = create_business(slug="tenant-b", name="Tenant B")
        create_membership(business_a, create_user(OWNER))
        create_membership(business_b, create_user(INTRUDER))

        owner_b_csrf = login_as(client, INTRUDER)
        b_category = _create_category(client, owner_b_csrf, business_b, name="B Cat")
        b_item = _create_item(client, owner_b_csrf, business_b, b_category["id"], name="B Item")

        csrf = login_as(client, OWNER)
        a_category = _create_category(client, csrf, business_a, name="A Cat")
        a_item = _create_item(client, csrf, business_a, a_category["id"], name="A Item")
        before = _audit_count(migrated_engine)

        # A's owner cannot see or touch B through B's business id...
        assert client.get(f"{_base(business_b)}/menu").status_code == 404
        assert client.get(f"{_base(business_b)}/items/{b_item['id']}").status_code == 404
        # ...nor reach B's objects through A's own business id (scoped
        # lookups): guessed cross-tenant ids do not disclose existence.
        assert client.get(f"{_base(business_a)}/items/{b_item['id']}").status_code == 404
        for response in (
            client.patch(
                f"{_base(business_a)}/categories/{b_category['id']}",
                json={"name": "Taken Over"},
                headers=csrf_headers(csrf),
            ),
            client.delete(f"{_base(business_a)}/items/{b_item['id']}", headers=csrf_headers(csrf)),
            client.post(
                f"{_base(business_a)}/categories/{b_category['id']}/items",
                json={"name": "Injected", "price_minor": 1},
                headers=csrf_headers(csrf),
            ),
            # Moving A's item into B's category must fail without disclosure.
            client.patch(
                f"{_base(business_a)}/items/{a_item['id']}",
                json={"category_id": b_category["id"]},
                headers=csrf_headers(csrf),
            ),
        ):
            assert response.status_code == 404
            assert _error_code(response) == "not_found"
        # Reorder with B's ids inside A's scope: exact-set mismatch, no leak.
        reorder = client.post(
            f"{_base(business_a)}/categories/reorder",
            json={"ordered_category_ids": [b_category["id"]]},
            headers=csrf_headers(csrf),
        )
        assert reorder.status_code == 409
        assert _audit_count(migrated_engine) == before, (
            "rejected cross-tenant attempts must not mutate audit"
        )

        # B's data is intact and B can still read it.
        login_as(client, INTRUDER)
        b_menu = _menu(client, business_b)
        assert [c["name"] for c in b_menu["categories"]] == ["B Cat"]
        assert [i["name"] for i in b_menu["categories"][0]["items"]] == ["B Item"]


def _menu_is_empty(client: TestClient, business_id: uuid.UUID) -> bool:
    return bool(_menu(client, business_id)["categories"] == [])
