"""Public availability contract, neutrality, and isolation (M5B, ADR-025).

Extends the permanent public-surface matrix (docs/04) to the hours
projection: only the Host selects a Business; only an **active** Business
answers; every failure is the same neutral 404; the response derives from
structured settings through the pure core; nothing is ever cacheable
(ruling D4).

Content assertions are deliberately time-robust: fixtures are around-the-
clock schedules, closures, or windows anchored to the tenant-local today,
so no assertion can flip with the wall clock. Instant-exact DST facts are
proven at the unit layer and through the member preview probe (M5A) —
never re-derived here from the real clock.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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

_AVAILABILITY = "/api/v1/public/availability"

ALWAYS_OPEN = [{"day_of_week": dow, "opens_minute": 0, "closes_minute": 1440} for dow in range(7)]


def _host(host: str = "shalik.localhost") -> dict[str, str]:
    return {"host": host}


def _get(client: TestClient, host: str = "shalik.localhost") -> Any:
    return client.get(_AVAILABILITY, headers=_host(host))


def _tenant_today(timezone: str = "America/New_York") -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(timezone)).date()


def _seed_hours(
    client: TestClient,
    business_id: uuid.UUID,
    *,
    weekly: list[dict[str, int]],
) -> str:
    csrf = login_as(client, OWNER)
    response = client.put(
        f"/api/v1/businesses/{business_id}/hours/weekly",
        json={"intervals": weekly},
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 200, response.text
    return csrf


class TestOrderingGate:
    """`ordering_enabled` (M6B, ADR-026 D12): entitlement AND pickup."""

    def _enable_pickup(self, client: TestClient, business_id: uuid.UUID) -> None:
        csrf = login_as(client, OWNER)
        response = client.put(
            f"/api/v1/businesses/{business_id}/hours/fulfillment",
            json={
                "pickup_enabled": True,
                "asap_enabled": True,
                "lead_time_minutes": 20,
                "slot_interval_minutes": 15,
                "last_order_before_close_minutes": 0,
                "max_days_ahead": 3,
            },
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200, response.text

    def _grant(self, engine: Engine, business_id: uuid.UUID) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO feature_entitlements (id, business_id, feature_key)"
                    " VALUES (:id, :bid, 'online_ordering')"
                ),
                {"id": str(uuid.uuid4()), "bid": str(business_id)},
            )

    def test_entitlement_and_pickup_together_enable_ordering(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        # Neither: off. The projection is live platform state, so each
        # half is added in turn against the same business.
        assert _get(client).json()["pickup"]["ordering_enabled"] is False
        self._enable_pickup(client, business_id)
        assert _get(client).json()["pickup"]["ordering_enabled"] is False
        self._grant(migrated_engine, business_id)
        assert _get(client).json()["pickup"]["ordering_enabled"] is True
        # Revocation switches it off instantly — the fact is computed
        # per request, never frozen into published content.
        with migrated_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM feature_entitlements WHERE business_id = :bid"),
                {"bid": str(business_id)},
            )
        assert _get(client).json()["pickup"]["ordering_enabled"] is False

    def test_entitlement_without_pickup_stays_off(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_business: CreateBusiness,
    ) -> None:
        business_id = create_business("shalik", status="active")
        self._grant(migrated_engine, business_id)
        body = _get(client).json()
        assert body["pickup"]["enabled"] is False
        assert body["pickup"]["ordering_enabled"] is False


class TestNeutralFailure:
    def _assert_neutral_404(self, response: Any) -> None:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_unknown_host_is_neutral_404(self, client: TestClient) -> None:
        self._assert_neutral_404(_get(client, "nope.localhost"))

    def test_non_active_lifecycles_are_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        for state in ("provisioning", "suspended", "closed"):
            create_business(f"biz-{state}", status=state)
            self._assert_neutral_404(_get(client, f"biz-{state}.localhost"))

    def test_malformed_reserved_apex_and_ip_hosts_are_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", status="active")
        for host in (
            "bad_host",
            "api.localhost",
            "localhost",
            "a.shalik.localhost",
            "127.0.0.1",
        ):
            self._assert_neutral_404(_get(client, host))


class TestProjection:
    def test_an_active_business_with_no_hours_is_honestly_closed(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", status="active")
        response = _get(client)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["business"] == {
            "name": "Demo Kitchen",
            "slug": "shalik",
            "timezone": "America/New_York",
            "currency": "USD",
        }
        assert body["is_open_now"] is False
        assert body["closes_at"] is None
        assert body["next_opens_at"] is None
        assert body["weekly"] == []
        assert body["exceptions"] == []
        assert body["pickup"] == {
            "enabled": False,
            "asap_enabled": True,
            "next_pickup_at": None,
            # M6B (ADR-026 D12): no pickup means no ordering, whatever
            # the entitlement says.
            "ordering_enabled": False,
            # M7A (ADR-027 D8): unpaused defaults — the effective facts.
            "ordering_paused": False,
            "pause_note": None,
            "pause_resumes_at": None,
        }

    def test_an_around_the_clock_schedule_is_open_now(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        _seed_hours(client, business_id, weekly=ALWAYS_OPEN)
        client.cookies.clear()

        body = _get(client).json()
        assert body["is_open_now"] is True
        assert body["closes_at"] is not None
        assert body["next_opens_at"] is None
        assert len(body["weekly"]) == 7
        assert body["weekly"][0] == {
            "day_of_week": 0,
            "opens_minute": 0,
            "closes_minute": 1440,
        }

    def test_a_closed_today_exception_defeats_the_weekly_schedule(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        csrf = _seed_hours(client, business_id, weekly=ALWAYS_OPEN)
        # Close today AND tomorrow in the tenant's local calendar, so the
        # assertion cannot flip if the run straddles local midnight.
        today = _tenant_today()
        for offset in (0, 1):
            target = (today + timedelta(days=offset)).isoformat()
            response = client.put(
                f"/api/v1/businesses/{business_id}/hours/exceptions/{target}",
                json={"intervals": [], "note": "Closed for Eid"},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200, response.text
        client.cookies.clear()

        body = _get(client).json()
        assert body["is_open_now"] is False
        # The projection lists the upcoming closures with the D6 note.
        listed = {e["exception_date"]: e for e in body["exceptions"]}
        assert listed[today.isoformat()]["intervals"] == []
        assert listed[today.isoformat()]["note"] == "Closed for Eid"
        # And the next opening resumes after the closed block.
        assert body["next_opens_at"] is not None

    def test_pickup_facts_follow_the_stored_policy(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        csrf = _seed_hours(client, business_id, weekly=ALWAYS_OPEN)
        response = client.put(
            f"/api/v1/businesses/{business_id}/hours/fulfillment",
            json={
                "pickup_enabled": True,
                "asap_enabled": False,
                "lead_time_minutes": 20,
                "slot_interval_minutes": 15,
                "last_order_before_close_minutes": 0,
                "max_days_ahead": 1,
            },
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200, response.text
        client.cookies.clear()

        body = _get(client).json()
        assert body["pickup"]["enabled"] is True
        assert body["pickup"]["asap_enabled"] is False
        # Around-the-clock hours: a valid pickup slot always exists.
        assert body["pickup"]["next_pickup_at"] is not None

    def test_the_exception_window_is_forward_and_bounded(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        csrf = _seed_hours(client, business_id, weekly=ALWAYS_OPEN)
        today = _tenant_today()
        past = (today - timedelta(days=5)).isoformat()
        near = (today + timedelta(days=5)).isoformat()
        far = (today + timedelta(days=120)).isoformat()  # beyond the 60-day window
        for target in (past, near, far):
            response = client.put(
                f"/api/v1/businesses/{business_id}/hours/exceptions/{target}",
                json={"intervals": []},
                headers=csrf_headers(csrf),
            )
            assert response.status_code == 200, response.text
        client.cookies.clear()

        listed = [e["exception_date"] for e in _get(client).json()["exceptions"]]
        assert near in listed
        assert past not in listed  # history is not display
        assert far not in listed  # beyond the public window


class TestHeadersAndMethod:
    def test_success_and_failure_are_never_cacheable(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", status="active")
        success = _get(client)
        assert success.status_code == 200
        # Ruling D4: no cache grant exists for this route — the global
        # no-store default applies to the success as well as every error.
        assert success.headers["Cache-Control"] == "no-store"
        failure = _get(client, "nope.localhost")
        assert failure.headers["Cache-Control"] == "no-store"

    def test_head_companion_answers_without_a_body(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business("shalik", status="active")
        response = client.head(_AVAILABILITY, headers=_host())
        assert response.status_code == 200
        assert response.content == b""


class TestIsolation:
    def test_each_host_answers_only_its_own_schedule(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        alpha = create_business("alpha", status="active")
        create_membership(alpha, create_user(OWNER), role="owner")
        _seed_hours(client, alpha, weekly=ALWAYS_OPEN)
        client.cookies.clear()
        create_business("bravo", status="active")  # never configured

        alpha_body = _get(client, "alpha.localhost").json()
        bravo_body = _get(client, "bravo.localhost").json()
        assert alpha_body["business"]["slug"] == "alpha"
        assert len(alpha_body["weekly"]) == 7
        assert bravo_body["business"]["slug"] == "bravo"
        assert bravo_body["weekly"] == []
        assert bravo_body["is_open_now"] is False

    def test_suspension_hides_availability_without_data_loss(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        _seed_hours(client, business_id, weekly=ALWAYS_OPEN)
        client.cookies.clear()
        assert _get(client).status_code == 200

        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'suspended' WHERE id = :bid"),
                {"bid": business_id},
            )
        assert _get(client).status_code == 404  # publicly gone…
        with migrated_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM business_hours WHERE business_id = :bid"),
                {"bid": business_id},
            ).scalar_one()
        assert count == 7  # …data intact
