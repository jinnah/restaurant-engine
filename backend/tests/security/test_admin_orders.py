"""The operational order surface: machine, authority, isolation, pause
(M7A, ADR-027).

The member half of the §7.7 machine as named commands (D1/D4): every
transition validates the current state inside the locked transaction,
appends the member-actor status event, and audits — an illegal command
is ``409 invalid_state`` carrying the current status. The D2 capability
(`business.orders.operate`) gates reads and commands for every role and
nobody else; slot-releasing refusals free capacity for a racing
placement (D3); the estimate (D7) and the pause vertical (D8) complete
the slice. Seeding reuses the M6A ordering fixture.
"""

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.core.errors import ApiError
from app.domains.identity.actor import ActorContext, AuthenticatedUser
from app.domains.orders import service as orders_service
from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)
from tests.security.test_public_orders import (
    OWNER,
    _payload,
    _place,
    _seed_ordering_business,
)

PLATFORM_ADMIN = "root@example.com"
STAFF = "staff@example.com"
MANAGER = "manager@example.com"


def _base(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/orders"


def _newest_order_id(client: TestClient, business_id: uuid.UUID) -> str:
    listed = client.get(_base(business_id), params={"limit": 1})
    assert listed.status_code == 200, listed.text
    return str(listed.json()["orders"][0]["id"])


def _seed_with_order(
    client: TestClient,
    engine: Engine,
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
    **seed_kwargs: Any,
) -> tuple[uuid.UUID, str, str, str]:
    """One placed order; returns (business_id, item_id, owner csrf, order_id)."""
    business_id, item_id, csrf = _seed_ordering_business(
        client, engine, create_user, create_business, create_membership, **seed_kwargs
    )
    placed = _place(client, _payload(item_id))
    assert placed.status_code == 201, placed.text
    # The public projection deliberately carries no order id (D4: a
    # tracking URL is shareable); the operational surface is where ids
    # live, so the seed reads its own list.
    return business_id, item_id, csrf, _newest_order_id(client, business_id)


def _set_placed_at(engine: Engine, business_id: uuid.UUID, order_number: int, instant: str) -> None:
    """Move one placed order in time, so a date filter has dates to find."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE orders SET placed_at = :instant"
                " WHERE business_id = :bid AND order_number = :number"
            ),
            {"instant": instant, "bid": str(business_id), "number": order_number},
        )


def _audit_rows(engine: Engine, business_id: uuid.UUID, action: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT actor_user_id, details FROM audit_events"
                " WHERE business_id = :bid AND action = :action ORDER BY id"
            ),
            {"bid": str(business_id), "action": action},
        ).mappings()
        return [dict(row) for row in rows]


class TestTransitions:
    def test_the_forward_path_events_and_audits_each_step(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, csrf, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        steps = [
            ("accept", "accepted", "order.accepted"),
            ("start-preparing", "preparing", "order.preparing"),
            ("mark-ready", "ready", "order.ready"),
            ("complete", "completed", "order.completed"),
        ]
        for command, expected_status, action in steps:
            response = client.post(
                f"{_base(business_id)}/{order_id}/{command}", headers=csrf_headers(csrf)
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == expected_status
            # The timeline is the append-only event trail (D7): creation
            # plus every member step so far, in order, member-attributed.
            assert body["timeline"][-1]["to_status"] == expected_status
            assert body["timeline"][-1]["actor_kind"] == "member"
            rows = _audit_rows(migrated_engine, business_id, action)
            assert len(rows) == 1
            assert rows[0]["actor_user_id"] is not None
            assert rows[0]["details"]["to_status"] == expected_status
        detail = client.get(f"{_base(business_id)}/{order_id}").json()
        assert [event["to_status"] for event in detail["timeline"]] == [
            "submitted",
            "accepted",
            "preparing",
            "ready",
            "completed",
        ]

    def test_an_illegal_command_is_invalid_state_with_the_current_status(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, csrf, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        # complete from submitted: two states early.
        response = client.post(
            f"{_base(business_id)}/{order_id}/complete", headers=csrf_headers(csrf)
        )
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "invalid_state"
        assert error["details"] == {"status": "submitted"}
        # The race shape (§19): the second device's duplicate accept.
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/accept", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )
        again = client.post(f"{_base(business_id)}/{order_id}/accept", headers=csrf_headers(csrf))
        assert again.status_code == 409
        assert again.json()["error"]["details"] == {"status": "accepted"}
        # Nothing corrupted: one accepted event, status still accepted.
        detail = client.get(f"{_base(business_id)}/{order_id}").json()
        assert detail["status"] == "accepted"
        assert [e["to_status"] for e in detail["timeline"]] == ["submitted", "accepted"]

    def test_member_cancel_is_legal_only_from_submitted(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, csrf, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/accept", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )
        refused = client.post(f"{_base(business_id)}/{order_id}/cancel", headers=csrf_headers(csrf))
        assert refused.status_code == 409
        assert refused.json()["error"]["details"] == {"status": "accepted"}

    def test_rejection_releases_the_slot_for_a_racing_placement(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, csrf, order_id = _seed_with_order(
            client,
            migrated_engine,
            create_user,
            create_business,
            create_membership,
            max_orders_per_slot=1,
        )
        # The slot is full: a second ASAP order refuses (D3-M6).
        second = _place(client, _payload(item_id))
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "slot_unavailable"
        # Rejection frees the capacity (D3-M7): the same placement now
        # succeeds — a refused order occupies no kitchen.
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/reject", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )
        third = _place(client, _payload(item_id))
        assert third.status_code == 201, third.text
        rows = _audit_rows(migrated_engine, business_id, "order.rejected")
        assert len(rows) == 1
        assert rows[0]["details"]["from_status"] == "submitted"


class TestAuthority:
    def test_every_role_operates_and_nonmembers_get_the_neutral_404(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, _, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        create_membership(business_id, create_user(STAFF), role="staff")
        create_membership(business_id, create_user(MANAGER), role="manager")
        # Staff hold the D2 capability: reads and the advance commands.
        staff_csrf = login_as(client, STAFF)
        assert client.get(_base(business_id)).status_code == 200
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/accept",
                headers=csrf_headers(staff_csrf),
            ).status_code
            == 200
        )
        manager_csrf = login_as(client, MANAGER)
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/start-preparing",
                headers=csrf_headers(manager_csrf),
            ).status_code
            == 200
        )
        # A platform administrator holds no membership: the same neutral
        # 404 as everywhere (D2).
        create_user(PLATFORM_ADMIN, is_platform_admin=True)
        admin_csrf = login_as(client, PLATFORM_ADMIN)
        assert client.get(_base(business_id)).status_code == 404
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/mark-ready",
                headers=csrf_headers(admin_csrf),
            ).status_code
            == 404
        )

    def test_cross_tenant_orders_do_not_exist(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, _, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        other_id = create_business("tandoor", status="active")
        create_membership(other_id, create_user("other-owner@example.com"), role="owner")
        other_csrf = login_as(client, "other-owner@example.com")
        # The foreign business's list is empty; its order ids resolve to
        # nothing under my tenant; my commands cannot reach them.
        listed = client.get(_base(other_id))
        assert listed.status_code == 200
        assert listed.json()["orders"] == []
        assert client.get(f"{_base(other_id)}/{order_id}").status_code == 404
        assert (
            client.post(
                f"{_base(other_id)}/{order_id}/accept", headers=csrf_headers(other_csrf)
            ).status_code
            == 404
        )
        # And my membership grants nothing on the other tenant's path.
        assert client.get(_base(business_id)).status_code == 404


class TestReads:
    def test_the_detail_carries_the_operational_projection(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, _, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        detail = client.get(f"{_base(business_id)}/{order_id}")
        assert detail.status_code == 200
        body = detail.json()
        # The counter's projection (D6): PII on purpose, plus today's
        # display constants and the event timeline.
        assert body["customer_name"] == "Amina Rahman"
        assert body["customer_phone"] == "(716) 555-0142"
        assert body["payment"] == "pay_at_pickup"
        assert body["source"] == "online"
        assert body["estimated_ready_at"] is None
        assert [e["to_status"] for e in body["timeline"]] == ["submitted"]
        assert body["lines"][0]["display_name"] == "Clay-oven lamb"

    def test_list_pages_newest_first_behind_the_exclusive_cursor(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _, _ = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        for _ in range(2):
            assert _place(client, _payload(item_id)).status_code == 201
        first_page = client.get(_base(business_id), params={"limit": 2}).json()
        assert [o["order_number"] for o in first_page["orders"]] == [3, 2]
        assert first_page["next_before_number"] == 2
        second_page = client.get(
            _base(business_id),
            params={"limit": 2, "before_number": first_page["next_before_number"]},
        ).json()
        assert [o["order_number"] for o in second_page["orders"]] == [1]
        assert second_page["next_before_number"] is None

    def test_filters_and_search_narrow_honestly(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, csrf, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        assert (
            _place(
                client,
                _payload(item_id, customer_name="Bashir Chowdhury"),
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/accept", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )
        by_status = client.get(_base(business_id), params={"status": "accepted"}).json()
        assert [o["order_number"] for o in by_status["orders"]] == [1]
        by_number = client.get(_base(business_id), params={"q": "2"}).json()
        assert [o["order_number"] for o in by_number["orders"]] == [2]
        # Name prefix, case-insensitive — also "customer order history".
        by_name = client.get(_base(business_id), params={"q": "bashir"}).json()
        assert [o["customer_name"] for o in by_name["orders"]] == ["Bashir Chowdhury"]
        by_phone = client.get(_base(business_id), params={"q": "(716)"}).json()
        assert len(by_phone["orders"]) == 2
        nothing = client.get(_base(business_id), params={"q": "zz-nobody"}).json()
        assert nothing["orders"] == []

    def test_the_day_filter_is_the_tenant_calendar_day(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        """A day means the restaurant's day, DST transition included (M7C).

        The chosen date is 2026-03-08, the US spring-forward Sunday: the
        local day is 23 hours long, so its window ends at 04:00Z on the
        9th. The second order sits at 04:30Z on the 9th — 00:30 local on
        the *next* day, and exactly the row a naive "midnight plus 24
        hours" window would have wrongly included.
        """
        business_id, item_id, _, _ = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        assert _place(client, _payload(item_id)).status_code == 201
        _set_placed_at(migrated_engine, business_id, 1, "2026-03-08T06:00:00+00:00")
        _set_placed_at(migrated_engine, business_id, 2, "2026-03-09T04:30:00+00:00")

        listed = client.get(_base(business_id), params={"day": "2026-03-08"}).json()
        assert [o["order_number"] for o in listed["orders"]] == [1]
        # The evening before, in local terms, belongs to the 7th.
        _set_placed_at(migrated_engine, business_id, 1, "2026-03-08T04:30:00+00:00")
        assert client.get(_base(business_id), params={"day": "2026-03-08"}).json()["orders"] == []
        seventh = client.get(_base(business_id), params={"day": "2026-03-07"}).json()
        assert [o["order_number"] for o in seventh["orders"]] == [1]

    def test_the_day_filter_narrows_an_explicit_window_rather_than_replacing_it(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _, _ = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        assert _place(client, _payload(item_id)).status_code == 201
        _set_placed_at(migrated_engine, business_id, 1, "2026-03-08T14:00:00+00:00")
        _set_placed_at(migrated_engine, business_id, 2, "2026-03-08T20:00:00+00:00")
        both = client.get(_base(business_id), params={"day": "2026-03-08"}).json()
        assert [o["order_number"] for o in both["orders"]] == [2, 1]
        # Neither filter is dropped: the tighter bound on each side wins.
        narrowed = client.get(
            _base(business_id),
            params={"day": "2026-03-08", "placed_after": "2026-03-08T18:00:00+00:00"},
        ).json()
        assert [o["order_number"] for o in narrowed["orders"]] == [2]


class TestEstimate:
    def test_set_show_clear_and_the_legal_states(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, csrf, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        estimate = (datetime.now(UTC) + timedelta(minutes=25)).isoformat()
        # Not before acceptance (D7).
        early = client.put(
            f"{_base(business_id)}/{order_id}/estimate",
            json={"estimated_ready_at": estimate},
            headers=csrf_headers(csrf),
        )
        assert early.status_code == 409
        assert early.json()["error"]["details"] == {"status": "submitted"}
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/accept", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )
        set_response = client.put(
            f"{_base(business_id)}/{order_id}/estimate",
            json={"estimated_ready_at": estimate},
            headers=csrf_headers(csrf),
        )
        assert set_response.status_code == 200
        assert set_response.json()["estimated_ready_at"] is not None
        rows = _audit_rows(migrated_engine, business_id, "order.estimate_set")
        assert len(rows) == 1
        assert rows[0]["details"]["estimate"] == "set"
        # The exact no-op writes nothing new.
        assert (
            client.put(
                f"{_base(business_id)}/{order_id}/estimate",
                json={"estimated_ready_at": estimate},
                headers=csrf_headers(csrf),
            ).status_code
            == 200
        )
        assert len(_audit_rows(migrated_engine, business_id, "order.estimate_set")) == 1
        # Clearing is audited as cleared.
        cleared = client.put(
            f"{_base(business_id)}/{order_id}/estimate",
            json={"estimated_ready_at": None},
            headers=csrf_headers(csrf),
        )
        assert cleared.status_code == 200
        assert cleared.json()["estimated_ready_at"] is None
        rows = _audit_rows(migrated_engine, business_id, "order.estimate_set")
        assert len(rows) == 2
        assert rows[1]["details"]["estimate"] == "cleared"

    def test_the_estimate_reaches_the_customer_tracker(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, csrf, _ = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        placed = _place(client, _payload(item_id))
        assert placed.status_code == 201
        token = placed.json()["tracking_token"]
        order_id = _newest_order_id(client, business_id)
        assert (
            client.post(
                f"{_base(business_id)}/{order_id}/accept", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )
        estimate = (datetime.now(UTC) + timedelta(minutes=20)).isoformat()
        assert (
            client.put(
                f"{_base(business_id)}/{order_id}/estimate",
                json={"estimated_ready_at": estimate},
                headers=csrf_headers(csrf),
            ).status_code
            == 200
        )
        tracked = client.get(f"/api/v1/public/orders/{token}", headers={"host": "shalik.localhost"})
        assert tracked.status_code == 200
        assert tracked.json()["estimated_ready_at"] is not None
        assert tracked.json()["status"] == "accepted"


class TestMetrics:
    def test_todays_numbers_are_computed_from_the_window(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, csrf, first_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        assert _place(client, _payload(item_id)).status_code == 201
        second = _newest_order_id(client, business_id)
        assert _place(client, _payload(item_id)).status_code == 201
        third = _newest_order_id(client, business_id)
        # first: accepted → ready (prep pair); second: rejected; third stands.
        for command in ("accept", "start-preparing", "mark-ready"):
            assert (
                client.post(
                    f"{_base(business_id)}/{first_id}/{command}",
                    headers=csrf_headers(csrf),
                ).status_code
                == 200
            )
        assert (
            client.post(
                f"{_base(business_id)}/{second}/reject", headers=csrf_headers(csrf)
            ).status_code
            == 200
        )
        assert third  # placed and left standing
        metrics = client.get(f"{_base(business_id)}/metrics")
        assert metrics.status_code == 200
        body = metrics.json()
        assert body["timezone"] == "America/New_York"
        # Money carries its unit (M7C): the strip never infers a currency
        # from a row, because on a quiet morning there is no row.
        assert body["currency"] == "USD"
        assert body["order_count"] == 3
        assert body["standing_order_count"] == 2
        assert body["sales_minor"] == 5000  # two standing x 2500
        assert body["average_order_value_minor"] == 2500
        assert body["rejected_count"] == 1
        assert body["cancelled_count"] == 0
        assert body["popular_items"] == [{"display_name": "Clay-oven lamb", "quantity": 6}]
        assert body["average_prep_seconds"] is not None
        assert body["average_prep_seconds"] >= 0


class TestPause:
    def test_pause_refuses_placement_with_the_visible_facts(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, csrf = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        resume_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        paused = client.put(
            f"/api/v1/businesses/{business_id}/hours/pause",
            json={"paused": True, "note": "Back after the dinner rush", "resume_at": resume_at},
            headers=csrf_headers(csrf),
        )
        assert paused.status_code == 200, paused.text
        assert paused.json()["fulfillment"]["ordering_paused"] is True
        # Placement refuses with the typed, deliberately NON-neutral 409
        # (D8): the surface exists and is honestly, temporarily off.
        refused = _place(client, _payload(item_id))
        assert refused.status_code == 409
        error = refused.json()["error"]
        assert error["code"] == "ordering_paused"
        assert error["details"]["note"] == "Back after the dinner rush"
        assert "resume_at" in error["details"]
        # The public projection carries the same effective facts; the
        # gate itself is unchanged — the surface still exists.
        availability = client.get(
            "/api/v1/public/availability", headers={"host": "shalik.localhost"}
        ).json()
        assert availability["pickup"]["ordering_enabled"] is True
        assert availability["pickup"]["ordering_paused"] is True
        assert availability["pickup"]["pause_note"] == "Back after the dinner rush"
        assert availability["pickup"]["pause_resumes_at"] is not None
        rows = _audit_rows(migrated_engine, business_id, "business.ordering_pause_set")
        assert len(rows) == 1
        assert rows[0]["details"]["ordering"] == "paused"
        assert rows[0]["details"]["note"] == "present"
        # Resume clears everything and placement works again.
        resumed = client.put(
            f"/api/v1/businesses/{business_id}/hours/pause",
            json={"paused": False},
            headers=csrf_headers(csrf),
        )
        assert resumed.status_code == 200
        assert resumed.json()["fulfillment"]["ordering_paused"] is False
        assert _place(client, _payload(item_id)).status_code == 201

    def test_an_expired_pause_reads_as_resumed(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, csrf = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        assert (
            client.put(
                f"/api/v1/businesses/{business_id}/hours/pause",
                json={"paused": True, "resume_at": past},
                headers=csrf_headers(csrf),
            ).status_code
            == 200
        )
        # Auto-resume is arithmetic (D8): placement succeeds and the
        # public facts read unpaused, while the STORED flag stays for
        # the workspace to show honestly.
        assert _place(client, _payload(item_id)).status_code == 201
        availability = client.get(
            "/api/v1/public/availability", headers={"host": "shalik.localhost"}
        ).json()
        assert availability["pickup"]["ordering_paused"] is False
        assert availability["pickup"]["pause_note"] is None

    def test_a_replay_still_reads_during_a_pause(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, csrf = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        payload = _payload(item_id)
        first = _place(client, payload)
        assert first.status_code == 201
        assert (
            client.put(
                f"/api/v1/businesses/{business_id}/hours/pause",
                json={"paused": True},
                headers=csrf_headers(csrf),
            ).status_code
            == 200
        )
        # The honest retry of a pre-pause order is a read (D2), and the
        # pause check deliberately sits after the replay lookup.
        replay = _place(client, payload)
        assert replay.status_code == 200
        assert replay.json()["order"]["order_number"] == 1

    def test_pause_coherence_and_authority(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        owner_csrf = login_as(client, OWNER)
        # A note without paused is a contradiction (schema-refused).
        assert (
            client.put(
                f"/api/v1/businesses/{business_id}/hours/pause",
                json={"paused": False, "note": "but why"},
                headers=csrf_headers(owner_csrf),
            ).status_code
            == 422
        )
        # Staff hold no hours-write authority: pausing is 403.
        create_membership(business_id, create_user(STAFF), role="staff")
        staff_csrf = login_as(client, STAFF)
        assert (
            client.put(
                f"/api/v1/businesses/{business_id}/hours/pause",
                json={"paused": True},
                headers=csrf_headers(staff_csrf),
            ).status_code
            == 403
        )


class TestConcurrentStaffActions:
    """Two staff devices on one order cannot corrupt it (blueprint §19).

    The proof is deterministic, not a sleep: transaction A takes the
    order-row lock the D1 commands take and moves the order itself;
    the production command then runs in a second session and must be
    seen *waiting on that lock* in ``pg_stat_activity`` before A
    commits. When A releases, B re-reads the row it now owns, finds a
    state its transition is illegal from, and refuses — appending
    nothing, auditing nothing.
    """

    def test_a_racing_second_accept_loses_honestly_and_changes_nothing(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, _, _, order_id = _seed_with_order(
            client, migrated_engine, create_user, create_business, create_membership
        )
        # The seed already made this owner; reuse the row rather than
        # colliding with the email uniqueness constraint.
        with migrated_engine.connect() as connection:
            owner_id = connection.execute(
                text("SELECT id FROM users WHERE email = :email"), {"email": OWNER}
            ).scalar_one()
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
                orders_service.transition_order(
                    session_b, actor, business_id, uuid.UUID(order_id), "accept"
                )
                outcome["result"] = "accepted"
            except ApiError as exc:
                outcome["result"] = (exc.status_code, exc.code.value, exc.details)
            except Exception as exc:  # pragma: no cover - diagnostic only
                outcome["result"] = ("unexpected", type(exc).__name__)
            finally:
                session_b.rollback()
                session_b.close()

        thread = threading.Thread(target=run_b)
        try:
            # A: the first device takes the order row and accepts it.
            locked = session_a.execute(
                text("SELECT status FROM orders WHERE id = :oid FOR UPDATE"),
                {"oid": order_id},
            ).scalar_one()
            assert locked == "submitted"
            session_a.execute(
                text("UPDATE orders SET status = 'accepted' WHERE id = :oid"),
                {"oid": order_id},
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
            assert observed_lock_wait, "the second command must block on the order row"
            assert "result" not in outcome, "B must not resolve while A holds the row"

            session_a.commit()  # releases the row; B proceeds
        finally:
            session_a.close()
            thread.join(timeout=15)
            assert not thread.is_alive(), "the blocked command must finish"

        # The loser is refused honestly, with the truth it must render.
        assert outcome["result"] == (409, "invalid_state", {"status": "accepted"})

        # And nothing of the order moved: one status event (the customer's
        # placement), no member event, no transition audit.
        with migrated_engine.connect() as connection:
            events = connection.execute(
                text(
                    "SELECT to_status, actor_kind FROM order_status_events"
                    " WHERE order_id = :oid ORDER BY occurred_at"
                ),
                {"oid": order_id},
            ).all()
        assert [(row[0], row[1]) for row in events] == [("submitted", "customer")]
        assert _audit_rows(migrated_engine, business_id, "order.accepted") == []
