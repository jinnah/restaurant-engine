"""Modifier behavior, authorization, and tenant isolation (M3B, ADR-017).

Extends the permanent isolation matrix to modifier groups and options and
proves the M3B rules: DB-enforced selection domain with computed
report-only satisfiability, the four count caps under the business lock,
dense compaction, exact-set no-op-suppressed reorders, availability in
the option PATCH, explicit max-mode audit details, cascade behavior with
no child-event fan-out, and real two-session lock serialization at the
groups-per-item boundary.
"""

import threading
import time
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.core.errors import ApiError
from app.domains.businesses.queries import lock_business_status
from app.domains.catalog import modifier_service, policies
from app.domains.catalog.schemas import ModifierGroupCreate
from app.domains.identity.actor import ActorContext, AuthenticatedUser
from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)
from tests.security.test_catalog import (
    OWNER,
    PLATFORM_ADMIN,
    STAFF,
    _audit_count,
    _audit_rows,
    _base,
    _create_category,
    _create_item,
    _error_code,
)

MANAGER = "modifier-manager@example.com"
INTRUDER = "modifier-intruder@example.com"


def _create_group(
    client: TestClient,
    csrf: str,
    business_id: uuid.UUID,
    item_id: str,
    name: str = "Spice Level",
    **extra: Any,
) -> dict[str, Any]:
    response = client.post(
        f"{_base(business_id)}/items/{item_id}/modifier-groups",
        json={"name": name, **extra},
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _create_option(
    client: TestClient,
    csrf: str,
    business_id: uuid.UUID,
    group_id: str,
    name: str = "Mild",
    **extra: Any,
) -> dict[str, Any]:
    response = client.post(
        f"{_base(business_id)}/modifier-groups/{group_id}/options",
        json={"name": name, **extra},
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _tree(client: TestClient, business_id: uuid.UUID, item_id: str) -> dict[str, Any]:
    response = client.get(f"{_base(business_id)}/items/{item_id}/modifier-groups")
    assert response.status_code == 200, response.text
    return dict(response.json())


def _workspace(
    client: TestClient,
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
) -> tuple[uuid.UUID, str, dict[str, Any]]:
    """Business + owner login + one item; returns (business, csrf, item)."""
    business = create_business()
    create_membership(business, create_user(OWNER))
    csrf = login_as(client, OWNER)
    category = _create_category(client, csrf, business)
    item = _create_item(client, csrf, business, category["id"])
    return business, csrf, item


class TestGroupConstruction:
    def test_zero_option_group_is_valid_and_unsatisfiable(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"], min_select=1)
        assert group["position"] == 0
        assert group["active_option_count"] == 0
        assert group["is_satisfiable"] is False
        assert group["options"] == []
        assert group["max_select"] is None

        # Legal-but-unsatisfiable configurations remain writable (D5).
        renamed = client.patch(
            f"{_base(business)}/modifier-groups/{group['id']}",
            json={"name": "Heat"},
            headers=csrf_headers(csrf),
        )
        assert renamed.status_code == 200

    def test_duplicate_group_name_case_insensitive(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        _create_group(client, csrf, business, item["id"], name="Spice Level")
        duplicate = client.post(
            f"{_base(business)}/items/{item['id']}/modifier-groups",
            json={"name": "SPICE level"},
            headers=csrf_headers(csrf),
        )
        assert duplicate.status_code == 409
        assert _error_code(duplicate) == "conflict"

    def test_effective_pair_validated_against_stored_values(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"], min_select=2)
        # Only max supplied; stored min=2 makes max=1 an invalid pair.
        response = client.patch(
            f"{_base(business)}/modifier-groups/{group['id']}",
            json={"max_select": 1},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422
        assert _error_code(response) == "validation_error"

    def test_explicit_null_max_sets_unlimited(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"], max_select=2)
        assert group["max_select"] == 2
        response = client.patch(
            f"{_base(business)}/modifier-groups/{group['id']}",
            json={"max_select": None},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert response.json()["max_select"] is None

    def test_noop_group_update_records_no_audit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        response = client.patch(
            f"{_base(business)}/modifier-groups/{group['id']}",
            json={"name": group["name"], "min_select": 0},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert _audit_rows(migrated_engine, business, "catalog.modifier_group_updated") == []


class TestSatisfiabilityTransitions:
    def test_full_transition_matrix(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"], min_select=2)
        gid = group["id"]

        # +1 active option: still short of min=2.
        view = _create_option(client, csrf, business, gid, name="Mild")
        assert view["active_option_count"] == 1
        assert view["is_satisfiable"] is False

        # +2nd option: satisfiable.
        view = _create_option(client, csrf, business, gid, name="Hot")
        assert view["active_option_count"] == 2
        assert view["is_satisfiable"] is True

        # Finite max above active options: unsatisfiable (docs/03).
        response = client.patch(
            f"{_base(business)}/modifier-groups/{gid}",
            json={"min_select": 0, "max_select": 5},
            headers=csrf_headers(csrf),
        )
        assert response.json()["is_satisfiable"] is False
        # Lower max to the active count: satisfiable again.
        response = client.patch(
            f"{_base(business)}/modifier-groups/{gid}",
            json={"max_select": 2},
            headers=csrf_headers(csrf),
        )
        assert response.json()["is_satisfiable"] is True

        # Disabling an option drops the active count below the finite max.
        mild_id = response.json()["options"][0]["id"]
        view_response = client.patch(
            f"{_base(business)}/modifier-options/{mild_id}",
            json={"is_available": False},
            headers=csrf_headers(csrf),
        )
        body = view_response.json()
        assert body["active_option_count"] == 1
        assert body["is_satisfiable"] is False

        # Re-enabling restores satisfiability.
        body = client.patch(
            f"{_base(business)}/modifier-options/{mild_id}",
            json={"is_available": True},
            headers=csrf_headers(csrf),
        ).json()
        assert body["active_option_count"] == 2
        assert body["is_satisfiable"] is True

        # Deleting the final options leaves the surviving group at zero.
        for option in list(body["options"]):
            body = client.delete(
                f"{_base(business)}/modifier-options/{option['id']}",
                headers=csrf_headers(csrf),
            ).json()
        assert body["active_option_count"] == 0
        assert body["is_satisfiable"] is False
        assert body["options"] == []


class TestOptions:
    def test_option_crud_and_parent_view(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        view = _create_option(
            client, csrf, business, group["id"], name="Extra Chicken", price_delta_minor=450
        )
        option = view["options"][0]
        assert option["price_delta_minor"] == 450
        assert option["is_available"] is True
        assert option["position"] == 0

        # Duplicate name (CI) within the group; same name in another group OK.
        duplicate = client.post(
            f"{_base(business)}/modifier-groups/{group['id']}/options",
            json={"name": "EXTRA chicken"},
            headers=csrf_headers(csrf),
        )
        assert duplicate.status_code == 409
        other_group = _create_group(client, csrf, business, item["id"], name="Add-ons")
        _create_option(client, csrf, business, other_group["id"], name="Extra Chicken")

        updated = client.patch(
            f"{_base(business)}/modifier-options/{option['id']}",
            json={"price_delta_minor": 500},
            headers=csrf_headers(csrf),
        )
        assert updated.status_code == 200
        events = _audit_rows(migrated_engine, business, "catalog.modifier_option_updated")
        assert len(events) == 1
        details = events[0]["details"]
        assert details["changed_fields"] == "price_delta_minor"
        assert details["price_delta_minor_old"] == 450
        assert details["price_delta_minor_new"] == 500
        # Stored details carry explicit nulls (M3A recorder precedent);
        # the typed read-time projection is what omits inapplicable keys.
        assert details["availability_old"] is None, (
            "availability fields appear only when availability changes"
        )

        # Deletion compacts sibling positions.
        second = _create_option(client, csrf, business, group["id"], name="Second")
        third_view = _create_option(client, csrf, business, group["id"], name="Third")
        assert [o["position"] for o in third_view["options"]] == [0, 1, 2]
        after_delete = client.delete(
            f"{_base(business)}/modifier-options/{second['options'][1]['id']}",
            headers=csrf_headers(csrf),
        ).json()
        assert [o["name"] for o in after_delete["options"]] == ["Extra Chicken", "Third"]
        assert [o["position"] for o in after_delete["options"]] == [0, 1]

    def test_noop_availability_patch_records_no_audit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        view = _create_option(client, csrf, business, group["id"])
        option_id = view["options"][0]["id"]
        response = client.patch(
            f"{_base(business)}/modifier-options/{option_id}",
            json={"is_available": True},  # already true
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert _audit_rows(migrated_engine, business, "catalog.modifier_option_updated") == []

    def test_availability_change_audits_the_closed_set_pair(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        view = _create_option(client, csrf, business, group["id"])
        option_id = view["options"][0]["id"]
        response = client.patch(
            f"{_base(business)}/modifier-options/{option_id}",
            json={"is_available": False},
            headers=csrf_headers(csrf),
        )
        assert response.json()["active_option_count"] == 0
        events = _audit_rows(migrated_engine, business, "catalog.modifier_option_updated")
        details = events[0]["details"]
        assert details["changed_fields"] == "is_available"
        assert details["availability_old"] == "available"
        assert details["availability_new"] == "unavailable"
        assert details["price_delta_minor_old"] is None


class TestReorders:
    def test_group_reorder_full_set_noop_and_mismatch(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        a = _create_group(client, csrf, business, item["id"], name="A")
        b = _create_group(client, csrf, business, item["id"], name="B")
        url = f"{_base(business)}/items/{item['id']}/modifier-groups/reorder"

        reordered = client.post(
            url,
            json={"ordered_group_ids": [b["id"], a["id"]]},
            headers=csrf_headers(csrf),
        )
        assert reordered.status_code == 200
        assert [g["id"] for g in reordered.json()["groups"]] == [b["id"], a["id"]]
        assert [g["position"] for g in reordered.json()["groups"]] == [0, 1]

        # Identical permutation: success, no writes, no second audit event.
        again = client.post(
            url,
            json={"ordered_group_ids": [b["id"], a["id"]]},
            headers=csrf_headers(csrf),
        )
        assert again.status_code == 200
        events = _audit_rows(migrated_engine, business, "catalog.modifier_groups_reordered")
        assert len(events) == 1
        assert events[0]["details"] == {"count": 2}

        mismatch = client.post(
            url,
            json={"ordered_group_ids": [a["id"]]},
            headers=csrf_headers(csrf),
        )
        assert mismatch.status_code == 409

    def test_option_reorder_within_group(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        _create_option(client, csrf, business, group["id"], name="One")
        view = _create_option(client, csrf, business, group["id"], name="Two")
        one_id, two_id = (o["id"] for o in view["options"])
        url = f"{_base(business)}/modifier-groups/{group['id']}/options/reorder"

        reordered = client.post(
            url,
            json={"ordered_option_ids": [two_id, one_id]},
            headers=csrf_headers(csrf),
        )
        assert reordered.status_code == 200
        assert [o["id"] for o in reordered.json()["options"]] == [two_id, one_id]

        again = client.post(
            url,
            json={"ordered_option_ids": [two_id, one_id]},
            headers=csrf_headers(csrf),
        )
        assert again.status_code == 200
        assert (
            len(_audit_rows(migrated_engine, business, "catalog.modifier_options_reordered")) == 1
        )


class TestGroupDeletionAndCascades:
    def test_group_delete_cascades_options_single_audit_event(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        first = _create_group(client, csrf, business, item["id"], name="First")
        second = _create_group(client, csrf, business, item["id"], name="Second")
        third = _create_group(client, csrf, business, item["id"], name="Third")
        _create_option(client, csrf, business, second["id"], name="A")
        _create_option(client, csrf, business, second["id"], name="B")

        response = client.delete(
            f"{_base(business)}/modifier-groups/{second['id']}",
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert response.json() == {"status": "deleted"}

        events = _audit_rows(migrated_engine, business, "catalog.modifier_group_deleted")
        assert len(events) == 1
        assert events[0]["details"]["option_count"] == 2
        # No per-option fan-out for the cascade.
        assert _audit_rows(migrated_engine, business, "catalog.modifier_option_deleted") == []
        with migrated_engine.begin() as connection:
            options_left = connection.execute(
                text("SELECT count(*) FROM modifier_options WHERE group_id = :gid"),
                {"gid": second["id"]},
            ).scalar_one()
        assert options_left == 0

        # Sibling group positions compact.
        tree = _tree(client, business, item["id"])
        assert [(g["name"], g["position"]) for g in tree["groups"]] == [
            (first["name"], 0),
            (third["name"], 1),
        ]

    def test_item_delete_cascades_modifiers_without_fanout(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        _create_option(client, csrf, business, group["id"])
        before = _audit_count(migrated_engine)

        deleted = client.delete(f"{_base(business)}/items/{item['id']}", headers=csrf_headers(csrf))
        assert deleted.status_code == 200
        with migrated_engine.begin() as connection:
            groups_left = connection.execute(
                text("SELECT count(*) FROM modifier_groups")
            ).scalar_one()
            options_left = connection.execute(
                text("SELECT count(*) FROM modifier_options")
            ).scalar_one()
        assert groups_left == 0 and options_left == 0
        # Exactly one new event: the item deletion. No modifier fan-out.
        assert _audit_count(migrated_engine) == before + 1
        assert len(_audit_rows(migrated_engine, business, "catalog.item_deleted")) == 1


class TestCountLimits:
    def test_groups_per_item_limit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                    " min_select, position) SELECT gen_random_uuid(), :bid, :iid,"
                    " 'bulk-group-' || n, 0, n FROM generate_series(0, :top) AS n"
                ),
                {
                    "bid": business,
                    "iid": item["id"],
                    "top": policies.MAX_MODIFIER_GROUPS_PER_ITEM - 1,
                },
            )
        response = client.post(
            f"{_base(business)}/items/{item['id']}/modifier-groups",
            json={"name": "One Too Many"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {
            "limit": policies.MAX_MODIFIER_GROUPS_PER_ITEM
        }

    def test_groups_per_business_limit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        per_item = policies.MAX_MODIFIER_GROUPS_PER_ITEM
        bulk_items = policies.MAX_MODIFIER_GROUPS_PER_BUSINESS // per_item
        with migrated_engine.begin() as connection:
            category_id = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Bulk', 1, true)"
                    " RETURNING id"
                ),
                {"bid": business},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " SELECT gen_random_uuid(), :bid, :cid, 'bulk-item-' || n, 500, n,"
                    " true, false, false FROM generate_series(0, :top) AS n"
                ),
                {"bid": business, "cid": category_id, "top": bulk_items - 1},
            )
            connection.execute(
                text(
                    "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                    " min_select, position) SELECT gen_random_uuid(), :bid, mi.id,"
                    " 'bulk-group-' || n, 0, n FROM menu_items mi,"
                    " generate_series(0, :per) AS n WHERE mi.business_id = :bid"
                    " AND mi.category_id = :cid"
                ),
                {"bid": business, "cid": category_id, "per": per_item - 1},
            )
        response = client.post(
            f"{_base(business)}/items/{item['id']}/modifier-groups",
            json={"name": "Overflow"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {
            "limit": policies.MAX_MODIFIER_GROUPS_PER_BUSINESS
        }

    def test_options_per_group_limit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO modifier_options (id, business_id, group_id, name,"
                    " price_delta_minor, is_available, position) SELECT"
                    " gen_random_uuid(), :bid, :gid, 'bulk-option-' || n, 0, true, n"
                    " FROM generate_series(0, :top) AS n"
                ),
                {
                    "bid": business,
                    "gid": group["id"],
                    "top": policies.MAX_MODIFIER_OPTIONS_PER_GROUP - 1,
                },
            )
        response = client.post(
            f"{_base(business)}/modifier-groups/{group['id']}/options",
            json={"name": "Overflow"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {
            "limit": policies.MAX_MODIFIER_OPTIONS_PER_GROUP
        }

    def test_options_per_business_limit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        target_group = _create_group(client, csrf, business, item["id"])
        per_group = policies.MAX_MODIFIER_OPTIONS_PER_GROUP
        bulk_groups = policies.MAX_MODIFIER_OPTIONS_PER_BUSINESS // per_group
        per_item = policies.MAX_MODIFIER_GROUPS_PER_ITEM
        bulk_items = -(-bulk_groups // per_item)  # ceil
        with migrated_engine.begin() as connection:
            category_id = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Bulk', 1, true)"
                    " RETURNING id"
                ),
                {"bid": business},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " SELECT gen_random_uuid(), :bid, :cid, 'bulk-item-' || n, 500, n,"
                    " true, false, false FROM generate_series(0, :top) AS n"
                ),
                {"bid": business, "cid": category_id, "top": bulk_items - 1},
            )
            # bulk_groups groups spread across the bulk items (10 per item).
            connection.execute(
                text(
                    "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                    " min_select, position) SELECT gen_random_uuid(), :bid, mi.id,"
                    " 'bulk-group-' || n, 0, n FROM menu_items mi,"
                    " generate_series(0, :per) AS n WHERE mi.business_id = :bid"
                    " AND mi.category_id = :cid"
                ),
                {"bid": business, "cid": category_id, "per": per_item - 1},
            )
            connection.execute(
                text(
                    "INSERT INTO modifier_options (id, business_id, group_id, name,"
                    " price_delta_minor, is_available, position) SELECT"
                    " gen_random_uuid(), :bid, mg.id, 'bulk-option-' || n, 0, true, n"
                    " FROM (SELECT id FROM modifier_groups WHERE business_id = :bid"
                    " AND name LIKE 'bulk-group-%' LIMIT :glimit) mg,"
                    " generate_series(0, :per) AS n"
                ),
                {
                    "bid": business,
                    "glimit": bulk_groups,
                    "per": per_group - 1,
                },
            )
        response = client.post(
            f"{_base(business)}/modifier-groups/{target_group['id']}/options",
            json={"name": "Overflow"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"] == {
            "limit": policies.MAX_MODIFIER_OPTIONS_PER_BUSINESS
        }


class TestGroupAuditModeTransitions:
    """D6 correction: the maximum mode is explicit, never inferred."""

    def test_create_details_finite_and_unlimited(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        _create_group(client, csrf, business, item["id"], name="Unlimited")
        _create_group(client, csrf, business, item["id"], name="Finite", max_select=3)
        events = _audit_rows(migrated_engine, business, "catalog.modifier_group_created")
        unlimited, finite = events[0]["details"], events[1]["details"]
        assert unlimited["max_select_mode"] == "unlimited"
        assert unlimited["max_select"] is None
        assert finite["max_select_mode"] == "finite"
        assert finite["max_select"] == 3

    def test_update_mode_transition_matrix(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"], max_select=3)
        url = f"{_base(business)}/modifier-groups/{group['id']}"

        # finite -> different finite: both modes, both values.
        client.patch(url, json={"max_select": 5}, headers=csrf_headers(csrf))
        # finite -> unlimited: both modes, old value only.
        client.patch(url, json={"max_select": None}, headers=csrf_headers(csrf))
        # unlimited -> finite: both modes, new value only.
        client.patch(url, json={"max_select": 2}, headers=csrf_headers(csrf))
        # min change: min old/new, no mode fields.
        client.patch(url, json={"min_select": 1}, headers=csrf_headers(csrf))

        events = _audit_rows(migrated_engine, business, "catalog.modifier_group_updated")
        finite_to_finite, finite_to_unlimited, unlimited_to_finite, min_change = (
            event["details"] for event in events
        )
        assert finite_to_finite["max_select_mode_old"] == "finite"
        assert finite_to_finite["max_select_mode_new"] == "finite"
        assert finite_to_finite["max_select_old"] == 3
        assert finite_to_finite["max_select_new"] == 5

        assert finite_to_unlimited["max_select_mode_old"] == "finite"
        assert finite_to_unlimited["max_select_mode_new"] == "unlimited"
        assert finite_to_unlimited["max_select_old"] == 5
        assert finite_to_unlimited["max_select_new"] is None

        assert unlimited_to_finite["max_select_mode_old"] == "unlimited"
        assert unlimited_to_finite["max_select_mode_new"] == "finite"
        assert unlimited_to_finite["max_select_old"] is None
        assert unlimited_to_finite["max_select_new"] == 2

        assert min_change["changed_fields"] == "min_select"
        assert min_change["min_select_old"] == 0
        assert min_change["min_select_new"] == 1
        assert min_change["max_select_mode_old"] is None

        # The API-level contract: the typed projection omits inapplicable
        # (null) keys entirely — the D6 field-presence rules bind here.
        trail = client.get(f"/api/v1/businesses/{business}/audit-events")
        assert trail.status_code == 200
        projected = [
            event["details"]
            for event in trail.json()["items"]
            if event["action"] == "catalog.modifier_group_updated"
        ]
        # id DESC: min_change, unlimited_to_finite, finite_to_unlimited, f2f.
        p_min, p_u2f, p_f2u, p_f2f = projected
        assert "max_select_mode_old" not in p_min
        assert "max_select_old" not in p_u2f and p_u2f["max_select_new"] == 2
        assert "max_select_new" not in p_f2u and p_f2u["max_select_old"] == 5
        assert p_f2f["max_select_old"] == 3 and p_f2f["max_select_new"] == 5


class TestAuditAtomicity:
    def test_commit_time_constraint_failure_rolls_back_mutation_and_audit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        """A seeded non-dense group position makes the API create collide at
        commit (DEFERRED unique) — after audit was recorded — so both roll
        back together."""
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                    " min_select, position) VALUES (gen_random_uuid(), :bid, :iid,"
                    " 'Seeded', 0, 1)"
                ),
                {"bid": business, "iid": item["id"]},
            )
        response = client.post(
            f"{_base(business)}/items/{item['id']}/modifier-groups",
            json={"name": "Doomed"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert _error_code(response) == "conflict"
        with migrated_engine.begin() as connection:
            rows = connection.execute(
                text("SELECT count(*) FROM modifier_groups WHERE name = 'Doomed'")
            ).scalar_one()
        assert rows == 0
        assert _audit_rows(migrated_engine, business, "catalog.modifier_group_created") == []


class TestAuthorizationMatrix:
    def test_anonymous_and_csrf(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        group = _create_group(client, csrf, business, item["id"])
        client.cookies.clear()
        assert (
            client.get(f"{_base(business)}/items/{item['id']}/modifier-groups").status_code == 401
        )
        login_as(client, OWNER)
        no_token = client.post(
            f"{_base(business)}/items/{item['id']}/modifier-groups",
            json={"name": "X"},
            headers={"Origin": "http://testserver"},
        )
        assert no_token.status_code == 403
        assert _error_code(no_token) == "csrf_rejected"
        assert group["id"]  # group untouched fixture reference

    def test_staff_have_no_modifier_authority_but_can_read(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business, csrf, item = _workspace(client, create_user, create_business, create_membership)
        create_membership(business, create_user(STAFF), role="staff")
        group = _create_group(client, csrf, business, item["id"])
        view = _create_option(client, csrf, business, group["id"])
        option_id = view["options"][0]["id"]

        staff_csrf = login_as(client, STAFF)
        before = _audit_count(migrated_engine)
        denied = [
            client.post(
                f"{_base(business)}/items/{item['id']}/modifier-groups",
                json={"name": "Staff Group"},
                headers=csrf_headers(staff_csrf),
            ),
            client.patch(
                f"{_base(business)}/modifier-groups/{group['id']}",
                json={"min_select": 1},
                headers=csrf_headers(staff_csrf),
            ),
            client.delete(
                f"{_base(business)}/modifier-groups/{group['id']}",
                headers=csrf_headers(staff_csrf),
            ),
            client.post(
                f"{_base(business)}/items/{item['id']}/modifier-groups/reorder",
                json={"ordered_group_ids": [group["id"]]},
                headers=csrf_headers(staff_csrf),
            ),
            client.post(
                f"{_base(business)}/modifier-groups/{group['id']}/options",
                json={"name": "Staff Option"},
                headers=csrf_headers(staff_csrf),
            ),
            # D4: staff cannot change modifier-option availability.
            client.patch(
                f"{_base(business)}/modifier-options/{option_id}",
                json={"is_available": False},
                headers=csrf_headers(staff_csrf),
            ),
            client.delete(
                f"{_base(business)}/modifier-options/{option_id}",
                headers=csrf_headers(staff_csrf),
            ),
            client.post(
                f"{_base(business)}/modifier-groups/{group['id']}/options/reorder",
                json={"ordered_option_ids": [option_id]},
                headers=csrf_headers(staff_csrf),
            ),
        ]
        for response in denied:
            assert response.status_code == 403
            assert _error_code(response) == "permission_denied"
        assert _audit_count(migrated_engine) == before

        # Reads stay available to staff (business.view).
        assert (
            client.get(f"{_base(business)}/items/{item['id']}/modifier-groups").status_code == 200
        )

    def test_manager_can_write_platform_admin_gets_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business = create_business()
        create_membership(business, create_user(MANAGER), role="manager")
        csrf = login_as(client, MANAGER)
        category = _create_category(client, csrf, business)
        item = _create_item(client, csrf, business, category["id"])
        group = _create_group(client, csrf, business, item["id"])
        assert group["position"] == 0

        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        admin_csrf = login_as(client, PLATFORM_ADMIN)
        assert (
            client.get(f"{_base(business)}/items/{item['id']}/modifier-groups").status_code == 404
        )
        response = client.post(
            f"{_base(business)}/items/{item['id']}/modifier-groups",
            json={"name": "Admin Group"},
            headers=csrf_headers(admin_csrf),
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
        business_a = create_business(slug="mod-tenant-a", name="Mod A")
        business_b = create_business(slug="mod-tenant-b", name="Mod B")
        create_membership(business_a, create_user(OWNER))
        create_membership(business_b, create_user(INTRUDER))

        b_csrf = login_as(client, INTRUDER)
        b_category = _create_category(client, b_csrf, business_b, name="B Cat")
        b_item = _create_item(client, b_csrf, business_b, b_category["id"], name="B Item")
        b_group = _create_group(client, b_csrf, business_b, b_item["id"], name="B Group")
        b_view = _create_option(client, b_csrf, business_b, b_group["id"], name="B Option")
        b_option = b_view["options"][0]

        csrf = login_as(client, OWNER)
        before = _audit_count(migrated_engine)
        # B's objects are unreachable through A's business id (scoped 404s).
        for response in (
            client.get(f"{_base(business_a)}/items/{b_item['id']}/modifier-groups"),
            client.post(
                f"{_base(business_a)}/items/{b_item['id']}/modifier-groups",
                json={"name": "Injected"},
                headers=csrf_headers(csrf),
            ),
            client.patch(
                f"{_base(business_a)}/modifier-groups/{b_group['id']}",
                json={"min_select": 1},
                headers=csrf_headers(csrf),
            ),
            client.delete(
                f"{_base(business_a)}/modifier-groups/{b_group['id']}",
                headers=csrf_headers(csrf),
            ),
            client.post(
                f"{_base(business_a)}/modifier-groups/{b_group['id']}/options",
                json={"name": "Injected"},
                headers=csrf_headers(csrf),
            ),
            client.patch(
                f"{_base(business_a)}/modifier-options/{b_option['id']}",
                json={"is_available": False},
                headers=csrf_headers(csrf),
            ),
            client.delete(
                f"{_base(business_a)}/modifier-options/{b_option['id']}",
                headers=csrf_headers(csrf),
            ),
        ):
            assert response.status_code == 404
            assert _error_code(response) == "not_found"
        assert _audit_count(migrated_engine) == before

        # B's data intact.
        login_as(client, INTRUDER)
        tree = _tree(client, business_b, b_item["id"])
        assert [g["name"] for g in tree["groups"]] == ["B Group"]
        assert tree["groups"][0]["options"][0]["name"] == "B Option"


class TestLifecycle:
    def test_suspended_editable_closed_immutable_readable(
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
        group = _create_group(client, csrf, business, item["id"])
        view = _create_option(client, csrf, business, group["id"])
        option_id = view["options"][0]["id"]

        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'suspended' WHERE id = :bid"),
                {"bid": business},
            )
        _create_group(client, csrf, business, item["id"], name="While Suspended")

        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'closed' WHERE id = :bid"),
                {"bid": business},
            )
        for attempt in (
            client.post(
                f"{_base(business)}/items/{item['id']}/modifier-groups",
                json={"name": "New"},
                headers=csrf_headers(csrf),
            ),
            client.patch(
                f"{_base(business)}/modifier-options/{option_id}",
                json={"is_available": False},
                headers=csrf_headers(csrf),
            ),
            client.delete(
                f"{_base(business)}/modifier-groups/{group['id']}",
                headers=csrf_headers(csrf),
            ),
        ):
            assert attempt.status_code == 409
            assert _error_code(attempt) == "invalid_state"
        # Reads remain available (closure retains data).
        assert (
            client.get(f"{_base(business)}/items/{item['id']}/modifier-groups").status_code == 200
        )


class TestBusinessLockSerializationForModifiers:
    """M3B concurrency evidence: the shared business lock serializes the
    groups-per-item boundary through the production modifier service."""

    def test_concurrent_group_creates_at_the_item_limit_serialize(
        self,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business = create_business()
        owner_id = create_user(OWNER)
        create_membership(business, owner_id)
        with migrated_engine.begin() as connection:
            category_id = connection.execute(
                text(
                    "INSERT INTO menu_categories (id, business_id, name, position,"
                    " is_visible) VALUES (gen_random_uuid(), :bid, 'Mains', 0, true)"
                    " RETURNING id"
                ),
                {"bid": business},
            ).scalar_one()
            item_id = connection.execute(
                text(
                    "INSERT INTO menu_items (id, business_id, category_id, name,"
                    " price_minor, position, is_available, is_hidden, is_featured)"
                    " VALUES (gen_random_uuid(), :bid, :cid, 'Curry', 900, 0, true,"
                    " false, false) RETURNING id"
                ),
                {"bid": business, "cid": category_id},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                    " min_select, position) SELECT gen_random_uuid(), :bid, :iid,"
                    " 'bulk-group-' || n, 0, n FROM generate_series(0, 8) AS n"
                ),
                {"bid": business, "iid": item_id},
            )  # 9 committed groups

        actor = ActorContext(
            user=AuthenticatedUser(
                id=owner_id,
                email=OWNER,
                display_name="Test User",
                is_platform_admin=False,
            ),
            session_id=uuid.uuid4(),
            csrf_token="test-csrf",
        )
        session_factory = sessionmaker(bind=migrated_engine)
        session_a = session_factory()
        outcome: dict[str, Any] = {}
        b_started = threading.Event()

        def run_b() -> None:
            session_b = session_factory()
            try:
                b_started.set()
                modifier_service.create_group(
                    session_b, actor, business, item_id, ModifierGroupCreate(name="Eleventh")
                )
                outcome["result"] = "created"
            except ApiError as exc:
                outcome["result"] = (exc.status_code, exc.code.value, exc.details)
            except Exception as exc:  # pragma: no cover - diagnostic only
                outcome["result"] = ("unexpected", type(exc).__name__)
            finally:
                session_b.rollback()
                session_b.close()

        thread = threading.Thread(target=run_b)
        try:
            assert lock_business_status(session_a, business) == "provisioning"
            session_a.execute(
                text(
                    "INSERT INTO modifier_groups (id, business_id, item_id, name,"
                    " min_select, position) VALUES (gen_random_uuid(), :bid, :iid,"
                    " 'Tenth', 0, 9)"
                ),
                {"bid": business, "iid": item_id},
            )
            thread.start()
            assert b_started.wait(timeout=5), "worker thread must start"

            deadline = time.monotonic() + 10
            observed_lock_wait = False
            while time.monotonic() < deadline:
                with migrated_engine.connect() as probe:
                    waiting = probe.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity"
                            " WHERE datname = current_database()"
                            " AND wait_event_type = 'Lock'"
                            " AND query LIKE '%FOR UPDATE%'"
                        )
                    ).scalar_one()
                if waiting:
                    observed_lock_wait = True
                    break
                time.sleep(0.05)
            assert observed_lock_wait, "B must block on the business-row lock"
            assert "result" not in outcome, "B must not complete while A holds the lock"

            session_a.commit()
        finally:
            # Close A first (rollback releases the lock so a blocked B can
            # always finish), then join the worker if it ever started.
            session_a.close()
            if thread.ident is not None:
                thread.join(timeout=10)
        assert not thread.is_alive(), "B must finish once the lock is released"

        assert outcome["result"] == (
            409,
            "conflict",
            {"limit": policies.MAX_MODIFIER_GROUPS_PER_ITEM},
        )
        with migrated_engine.begin() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM modifier_groups WHERE item_id = :iid"),
                {"iid": item_id},
            ).scalar_one()
            stray = connection.execute(
                text("SELECT count(*) FROM modifier_groups WHERE name = 'Eleventh'")
            ).scalar_one()
            idle_in_transaction = connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database()"
                    " AND state = 'idle in transaction'"
                )
            ).scalar_one()
        assert count == 10, "A's committed 10th group is the final state"
        assert stray == 0, "B's rejected group must not exist"
        assert _audit_rows(migrated_engine, business, "catalog.modifier_group_created") == []
        assert idle_in_transaction == 0, "no connection may leak a transaction"
