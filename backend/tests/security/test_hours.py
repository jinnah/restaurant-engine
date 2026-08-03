"""Hours administration behavior, authorization, and isolation (M5A, ADR-025).

Extends the permanent isolation matrix (docs/04) to the three hours
tables and proves the service rules: full-set replacement semantics with
exact no-op suppression, the exception window and replacement precedence,
fulfillment defaults projected on read and materialized on first write,
lifecycle gating (closed businesses readable, immutable), the D7 read
capability split (staff read, owner/manager write), the member preview's
wiring to the pure DST core, and the D2 platform timezone command.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

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

WEEKDAYS = [
    {"day_of_week": dow, "opens_minute": 11 * 60, "closes_minute": 21 * 60} for dow in range(5)
]
FULFILLMENT = {
    "pickup_enabled": True,
    "asap_enabled": True,
    "lead_time_minutes": 25,
    "slot_interval_minutes": 15,
    "last_order_before_close_minutes": 30,
    "max_days_ahead": 3,
}


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/hours"


def _error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _future_date(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _audit_rows(engine: Engine, business_id: uuid.UUID, action: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT action, target_type, target_id, details FROM audit_events"
                " WHERE business_id = :bid AND action = :action ORDER BY id"
            ),
            {"bid": business_id, "action": action},
        )
        return [dict(row._mapping) for row in rows]


def _owner_business(
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
    client: TestClient,
    *,
    status: str = "active",
    slug: str = "demo-kitchen",
) -> tuple[uuid.UUID, str]:
    user_id = create_user(OWNER)
    business_id = create_business(slug, status=status)
    create_membership(business_id, user_id, role="owner")
    return business_id, login_as(client, OWNER)


class TestAuthorization:
    def test_unauthenticated_read_is_401(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        business_id = create_business()
        assert client.get(_base(business_id)).status_code == 401

    def test_every_member_role_reads(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business(status="active")
        for email, role in ((OWNER, "owner"), (MANAGER, "manager"), (STAFF, "staff")):
            create_membership(business_id, create_user(email), role=role)
        for email in (OWNER, MANAGER, STAFF):
            login_as(client, email)
            response = client.get(_base(business_id))
            assert response.status_code == 200, (email, response.text)
            client.cookies.clear()

    def test_owner_and_manager_write_but_staff_cannot(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business(status="active")
        for email, role in ((OWNER, "owner"), (MANAGER, "manager"), (STAFF, "staff")):
            create_membership(business_id, create_user(email), role=role)
        for email in (OWNER, MANAGER):
            csrf = login_as(client, email)
            response = client.put(
                f"{_base(business_id)}/weekly",
                json={"intervals": WEEKDAYS},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200, (email, response.text)
            client.cookies.clear()
        csrf = login_as(client, STAFF)
        response = client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": WEEKDAYS},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 403
        assert _error_code(response) == "permission_denied"

    def test_nonmembers_get_404_including_platform_admins(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business(status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        other = create_business("other-kitchen", status="active")
        create_membership(other, create_user(INTRUDER), role="owner")
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        for email in (INTRUDER, PLATFORM_ADMIN):
            csrf = login_as(client, email)
            assert client.get(_base(business_id)).status_code == 404, email
            response = client.put(
                f"{_base(business_id)}/weekly",
                json={"intervals": []},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 404, email
            client.cookies.clear()


class TestWeeklySchedule:
    def test_replacement_round_trips_canonically(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        # Submitted deliberately unsorted; stored and returned canonical.
        scrambled = [WEEKDAYS[3], WEEKDAYS[0], WEEKDAYS[4], WEEKDAYS[1], WEEKDAYS[2]]
        response = client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": scrambled},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200, response.text
        assert response.json()["weekly"] == WEEKDAYS
        assert client.get(_base(business_id)).json()["weekly"] == WEEKDAYS

    def test_replacement_is_exact_and_empties(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": WEEKDAYS},
            headers=csrf_headers(csrf),
        )
        response = client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": []},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert response.json()["weekly"] == []

    def test_exact_noop_writes_no_audit(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        for _ in range(2):
            response = client.put(
                f"{_base(business_id)}/weekly",
                json={"intervals": WEEKDAYS},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200
        rows = _audit_rows(migrated_engine, business_id, "business.hours_updated")
        assert len(rows) == 1
        assert rows[0]["details"] == {"interval_count": 5}

    def test_overlap_within_a_day_is_rejected(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        response = client.put(
            f"{_base(business_id)}/weekly",
            json={
                "intervals": [
                    {"day_of_week": 0, "opens_minute": 660, "closes_minute": 900},
                    {"day_of_week": 0, "opens_minute": 840, "closes_minute": 1260},
                ]
            },
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422

    def test_an_overnight_interval_collides_with_the_next_morning(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        response = client.put(
            f"{_base(business_id)}/weekly",
            json={
                "intervals": [
                    {"day_of_week": 0, "opens_minute": 20 * 60, "closes_minute": 26 * 60},
                    {"day_of_week": 1, "opens_minute": 60, "closes_minute": 540},
                ]
            },
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422

    def test_touching_intervals_are_legal(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        response = client.put(
            f"{_base(business_id)}/weekly",
            json={
                "intervals": [
                    {"day_of_week": 0, "opens_minute": 660, "closes_minute": 840},
                    {"day_of_week": 0, "opens_minute": 840, "closes_minute": 1260},
                ]
            },
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200

    def test_per_day_interval_limit(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        five = [
            {
                "day_of_week": 0,
                "opens_minute": hour * 60,
                "closes_minute": hour * 60 + 30,
            }
            for hour in (8, 10, 12, 14, 16)
        ]
        response = client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": five},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422

    def test_malformed_intervals_are_rejected(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        for bad in (
            {"day_of_week": 7, "opens_minute": 600, "closes_minute": 700},
            {"day_of_week": 0, "opens_minute": 700, "closes_minute": 700},
            {"day_of_week": 0, "opens_minute": 1440, "closes_minute": 1500},
            {"day_of_week": 0, "opens_minute": 600, "closes_minute": 2880},
            {"day_of_week": 0, "opens_minute": 0, "closes_minute": 1441},
        ):
            response = client.put(
                f"{_base(business_id)}/weekly",
                json={"intervals": [bad]},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 422, bad


class TestExceptions:
    def test_special_hours_and_closure_round_trip(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        special = _future_date(10)
        closed = _future_date(11)
        response = client.put(
            f"{_base(business_id)}/exceptions/{special}",
            json={
                "intervals": [{"opens_minute": 600, "closes_minute": 900}],
                "note": "Holiday hours",
            },
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200, response.text
        response = client.put(
            f"{_base(business_id)}/exceptions/{closed}",
            json={"intervals": [], "note": "Closed for Eid"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200, response.text
        stored = client.get(_base(business_id)).json()["exceptions"]
        assert stored == [
            {
                "exception_date": special,
                "intervals": [{"opens_minute": 600, "closes_minute": 900}],
                "note": "Holiday hours",
            },
            {"exception_date": closed, "intervals": [], "note": "Closed for Eid"},
        ]

    def test_replacement_is_per_date_and_exact(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        target = _future_date(10)
        client.put(
            f"{_base(business_id)}/exceptions/{target}",
            json={
                "intervals": [
                    {"opens_minute": 600, "closes_minute": 900},
                    {"opens_minute": 1000, "closes_minute": 1200},
                ]
            },
            headers=csrf_headers(csrf),
        )
        response = client.put(
            f"{_base(business_id)}/exceptions/{target}",
            json={"intervals": [{"opens_minute": 660, "closes_minute": 840}]},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        (stored,) = response.json()["exceptions"]
        assert stored["intervals"] == [{"opens_minute": 660, "closes_minute": 840}]

    def test_note_is_normalized_and_bounded(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        target = _future_date(10)
        response = client.put(
            f"{_base(business_id)}/exceptions/{target}",
            json={"intervals": [], "note": "  Closed   for  Eid  "},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200
        assert response.json()["exceptions"][0]["note"] == "Closed for Eid"
        for bad_note in ("x" * 121, "line\x00break"):
            response = client.put(
                f"{_base(business_id)}/exceptions/{target}",
                json={"intervals": [], "note": bad_note},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 422, bad_note

    def test_the_editable_window_is_enforced(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        too_far_past = (date.today() - timedelta(days=45)).isoformat()
        too_far_future = (date.today() + timedelta(days=600)).isoformat()
        for target in (too_far_past, too_far_future):
            response = client.put(
                f"{_base(business_id)}/exceptions/{target}",
                json={"intervals": []},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 422, target
            assert _error_code(response) == "validation_error"

    def test_noop_writes_no_audit_and_delete_removes(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        target = _future_date(10)
        payload = {"intervals": [], "note": "Closed for Eid"}
        for _ in range(2):
            response = client.put(
                f"{_base(business_id)}/exceptions/{target}",
                json=payload,
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200
        set_rows = _audit_rows(migrated_engine, business_id, "business.schedule_exception_set")
        assert len(set_rows) == 1
        # The note's *content* never enters the audit payload (D6).
        assert set_rows[0]["details"] == {
            "exception_date": target,
            "kind": "closed_all_day",
            "interval_count": 0,
            "note": "present",
        }
        response = client.delete(
            f"{_base(business_id)}/exceptions/{target}", headers=csrf_headers(csrf)
        )
        assert response.status_code == 200
        assert client.get(_base(business_id)).json()["exceptions"] == []
        removed_rows = _audit_rows(
            migrated_engine, business_id, "business.schedule_exception_removed"
        )
        assert [row["details"] for row in removed_rows] == [{"exception_date": target}]

    def test_deleting_an_absent_exception_is_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        response = client.delete(
            f"{_base(business_id)}/exceptions/{_future_date(10)}",
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 404


class TestFulfillment:
    def test_defaults_project_without_a_row(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = _owner_business(create_user, create_business, create_membership, client)
        fulfillment = client.get(_base(business_id)).json()["fulfillment"]
        assert fulfillment == {
            "pickup_enabled": False,
            "asap_enabled": True,
            "lead_time_minutes": 20,
            "slot_interval_minutes": 15,
            "last_order_before_close_minutes": 30,
            "max_days_ahead": 0,
            # M6A (ADR-026 D3): no cap by default — throttling is an
            # explicit operational choice.
            "max_orders_per_slot": None,
            "ordering_paused": False,
            "pause_note": None,
            "pause_resume_at": None,
            "is_configured": False,
        }
        with migrated_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM fulfillment_settings WHERE business_id = :bid"),
                {"bid": business_id},
            ).scalar_one()
        assert count == 0  # reads never materialize the row

    def test_first_write_materializes_and_noop_suppresses(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        for _ in range(2):
            response = client.put(
                f"{_base(business_id)}/fulfillment",
                json=FULFILLMENT,
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200, response.text
            # A document predating max_orders_per_slot (the delivered M5C
            # form) omits it; omission is the null it defaults to (M6A).
            assert response.json()["fulfillment"] == {
                **FULFILLMENT,
                "max_orders_per_slot": None,
                # M7A (ADR-027 D8): unpaused defaults — the fulfillment
                # document never carries the pause fields; only the
                # dedicated pause command writes them.
                "ordering_paused": False,
                "pause_note": None,
                "pause_resume_at": None,
                "is_configured": True,
            }
        rows = _audit_rows(migrated_engine, business_id, "business.fulfillment_updated")
        assert len(rows) == 1
        assert rows[0]["details"] == {
            "pickup": "enabled",
            "asap": "enabled",
            "lead_time_minutes": 25,
            "slot_interval_minutes": 15,
            "last_order_before_close_minutes": 30,
            "max_days_ahead": 3,
            "max_orders_per_slot": None,
        }

    def test_bounds_are_schema_enforced(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        for field, value in (
            ("lead_time_minutes", 1441),
            ("slot_interval_minutes", 4),
            ("slot_interval_minutes", 121),
            ("last_order_before_close_minutes", 241),
            ("max_days_ahead", 31),
            # M6A (ADR-026 D3): null means unlimited; zero and above-cap
            # are rejected, never coerced.
            ("max_orders_per_slot", 0),
            ("max_orders_per_slot", 101),
        ):
            response = client.put(
                f"{_base(business_id)}/fulfillment",
                json={**FULFILLMENT, field: value},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 422, (field, value)

    def test_partial_documents_are_rejected(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        partial = {k: v for k, v in FULFILLMENT.items() if k != "lead_time_minutes"}
        response = client.put(
            f"{_base(business_id)}/fulfillment",
            json=partial,
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422


class TestLifecycle:
    def test_closed_business_reads_but_refuses_every_mutation(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(
            create_user, create_business, create_membership, client, status="closed"
        )
        assert client.get(_base(business_id)).status_code == 200
        target = _future_date(10)
        attempts = (
            client.put(
                f"{_base(business_id)}/weekly",
                json={"intervals": WEEKDAYS},
                headers=csrf_headers(csrf),
            ),
            client.put(
                f"{_base(business_id)}/exceptions/{target}",
                json={"intervals": []},
                headers=csrf_headers(csrf),
            ),
            client.delete(f"{_base(business_id)}/exceptions/{target}", headers=csrf_headers(csrf)),
            client.put(
                f"{_base(business_id)}/fulfillment",
                json=FULFILLMENT,
                headers=csrf_headers(csrf),
            ),
        )
        for response in attempts:
            assert response.status_code == 409, response.text
            assert _error_code(response) == "invalid_state"

    def test_provisioning_and_suspended_stay_editable(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        for status, slug in (("provisioning", "prov-kitchen"), ("suspended", "susp-kitchen")):
            user = create_user(f"{status}@example.com")
            business_id = create_business(slug, status=status)
            create_membership(business_id, user, role="owner")
            csrf = login_as(client, f"{status}@example.com")
            response = client.put(
                f"{_base(business_id)}/weekly",
                json={"intervals": WEEKDAYS},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200, (status, response.text)
            client.cookies.clear()


class TestPreview:
    def test_preview_reflects_schedule_and_dst(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        # Sunday 01:00-03:00; on the 2026-03-08 spring-forward the wall
        # hour 02:00-03:00 does not exist, so the realized close is 03:00
        # EDT = 07:00Z — the pure core, proven through the API.
        client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": [{"day_of_week": 6, "opens_minute": 60, "closes_minute": 180}]},
            headers=csrf_headers(csrf),
        )
        response = client.get(
            f"{_base(business_id)}/preview",
            params={"at": "2026-03-08T06:30:00Z"},
        )
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["timezone"] == "America/New_York"
        assert preview["is_open_now"] is True
        assert _iso(preview["closes_at"]) == datetime(2026, 3, 8, 7, tzinfo=UTC)
        assert preview["next_opens_at"] is None
        assert preview["next_pickup_at"] is None  # pickup defaults disabled

    def test_preview_exercises_exceptions_and_pickup(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": WEEKDAYS},
            headers=csrf_headers(csrf),
        )
        client.put(
            f"{_base(business_id)}/fulfillment",
            json=FULFILLMENT,
            headers=csrf_headers(csrf),
        )
        # Next Monday inside the window, closed by exception.
        target = date.today() + timedelta(days=7 - date.today().weekday())
        client.put(
            f"{_base(business_id)}/exceptions/{target.isoformat()}",
            json={"intervals": []},
            headers=csrf_headers(csrf),
        )
        at = datetime(target.year, target.month, target.day, 17, 0, tzinfo=UTC)
        response = client.get(f"{_base(business_id)}/preview", params={"at": at.isoformat()})
        assert response.status_code == 200
        preview = response.json()
        assert preview["is_open_now"] is False
        # The next opening and pickup land on the following weekly day.
        assert preview["next_opens_at"] is not None
        assert preview["next_pickup_at"] is not None

    def test_naive_instants_are_rejected(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _ = _owner_business(create_user, create_business, create_membership, client)
        response = client.get(f"{_base(business_id)}/preview", params={"at": "2026-03-08T06:30:00"})
        assert response.status_code == 422
        assert _error_code(response) == "validation_error"


class TestIsolation:
    def test_hours_do_not_cross_tenants(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_a = create_business("kitchen-a", status="active")
        create_membership(business_a, create_user(OWNER), role="owner")
        business_b = create_business("kitchen-b", status="active")
        create_membership(business_b, create_user(INTRUDER), role="owner")

        csrf = login_as(client, OWNER)
        client.put(
            f"{_base(business_a)}/weekly",
            json={"intervals": WEEKDAYS},
            headers=csrf_headers(csrf),
        )
        client.cookies.clear()

        intruder_csrf = login_as(client, INTRUDER)
        # B's owner can neither read nor write A's hours; existence is not
        # disclosed (404, not 403).
        assert client.get(_base(business_a)).status_code == 404
        response = client.put(
            f"{_base(business_a)}/weekly",
            json={"intervals": []},
            headers=csrf_headers(intruder_csrf),
        )
        assert response.status_code == 404
        # …and B writing its own hours leaves A's untouched.
        client.put(
            f"{_base(business_b)}/weekly",
            json={"intervals": [{"day_of_week": 5, "opens_minute": 540, "closes_minute": 1020}]},
            headers=csrf_headers(intruder_csrf),
        )
        client.cookies.clear()
        login_as(client, OWNER)
        assert client.get(_base(business_a)).json()["weekly"] == WEEKDAYS
        with migrated_engine.connect() as connection:
            rows = connection.execute(
                text("SELECT business_id, count(*) FROM business_hours GROUP BY business_id")
            ).all()
        assert {str(row[0]): row[1] for row in rows} == {
            str(business_a): 5,
            str(business_b): 1,
        }

    def test_suspension_preserves_hours_rows(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": WEEKDAYS},
            headers=csrf_headers(csrf),
        )
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'suspended' WHERE id = :bid"),
                {"bid": business_id},
            )
        # The member still reads the schedule; the rows are intact.
        assert client.get(_base(business_id)).json()["weekly"] == WEEKDAYS


class TestPlatformTimezone:
    def test_platform_sets_audits_and_noops(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        business_id = create_business(status="active")
        csrf = login_as(client, PLATFORM_ADMIN)
        url = f"/api/v1/platform/businesses/{business_id}/timezone"
        response = client.put(url, json={"timezone": "America/Chicago"}, headers=csrf_headers(csrf))
        assert response.status_code == 200, response.text
        assert response.json()["timezone"] == "America/Chicago"
        # The exact no-op writes nothing.
        response = client.put(url, json={"timezone": "America/Chicago"}, headers=csrf_headers(csrf))
        assert response.status_code == 200
        rows = _audit_rows(migrated_engine, business_id, "business.timezone_changed")
        assert [row["details"] for row in rows] == [
            {"timezone_from": "America/New_York", "timezone_to": "America/Chicago"}
        ]

    def test_owner_cannot_reach_the_platform_command(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        response = client.put(
            f"/api/v1/platform/businesses/{business_id}/timezone",
            json={"timezone": "America/Chicago"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 403

    def test_unknown_zone_closed_business_and_missing_business(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        csrf = login_as(client, PLATFORM_ADMIN)
        active = create_business("active-kitchen", status="active")
        response = client.put(
            f"/api/v1/platform/businesses/{active}/timezone",
            json={"timezone": "America/Atlantis"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422
        closed = create_business("closed-kitchen", status="closed")
        response = client.put(
            f"/api/v1/platform/businesses/{closed}/timezone",
            json={"timezone": "America/Chicago"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert _error_code(response) == "invalid_state"
        response = client.put(
            f"/api/v1/platform/businesses/{uuid.uuid4()}/timezone",
            json={"timezone": "America/Chicago"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 404

    def test_the_change_reinterprets_stored_local_times(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, csrf = _owner_business(create_user, create_business, create_membership, client)
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        client.put(
            f"{_base(business_id)}/weekly",
            json={"intervals": WEEKDAYS},
            headers=csrf_headers(csrf),
        )
        # Monday 16:30Z: 11:30 New York (open) but 10:30 Chicago (closed).
        at = "2026-01-05T16:30:00Z"
        before = client.get(f"{_base(business_id)}/preview", params={"at": at}).json()
        assert before["is_open_now"] is True
        client.cookies.clear()
        admin_csrf = login_as(client, PLATFORM_ADMIN)
        client.put(
            f"/api/v1/platform/businesses/{business_id}/timezone",
            json={"timezone": "America/Chicago"},
            headers=csrf_headers(admin_csrf),
        )
        client.cookies.clear()
        login_as(client, OWNER)
        after = client.get(f"{_base(business_id)}/preview", params={"at": at}).json()
        assert after["timezone"] == "America/Chicago"
        assert after["is_open_now"] is False
