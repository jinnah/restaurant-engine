"""Guest order placement: contract, idempotency, neutrality, isolation
(M6A, ADR-026).

The public-surface matrix (docs/04) extended to the first unsafe public
route: only the Host selects a Business; only an active, entitled,
pickup-enabled Business accepts orders (placement ineligibility is the
one neutral 404 — ruling D10); the fail-closed browser-context check
guards the POST (ADR-010 + D9 self-origin); totals are authoritative;
retries cannot duplicate (ruling D2); the D3 slot throttle counts
non-cancelled orders; and nothing is ever cacheable.

Time-robustness: every fixture is an around-the-clock schedule with a
multi-day horizon, so ASAP always has a promise and the computed grid
slot below is valid whenever the suite runs. Instant-exact DST facts
stay in the hours unit matrix.
"""

import uuid
from datetime import UTC, datetime, timedelta
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

_ORDERS = "/api/v1/public/orders"

ALWAYS_OPEN = [{"day_of_week": dow, "opens_minute": 0, "closes_minute": 1440} for dow in range(7)]


# Anonymous browser evidence: the tenant page posting to its own origin.
def _public_headers(host: str = "shalik.localhost") -> dict[str, str]:
    return {"host": host, "sec-fetch-site": "same-origin"}


def _grid_slot(*, offset_slots: int = 2) -> datetime:
    """A near-future instant on the 15-minute grid of an always-open
    New York schedule (whole-hour UTC offset, so UTC quarters align)."""
    now = datetime.now(UTC)
    floor = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    return floor + timedelta(minutes=15 * offset_slots)


def _payload(item_id: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "idempotency_key": str(uuid.uuid4()),
        "lines": [{"item_id": item_id, "quantity": 2}],
        "customer_name": "Amina Rahman",
        "customer_phone": "(716) 555-0142",
        "consent_updates": True,
        "consent_marketing": False,
        "pickup_kind": "asap",
        "expected_total_minor": 2500,
    }
    base.update(overrides)
    return base


def _grant_online_ordering(engine: Engine, business_id: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO feature_entitlements (id, business_id, feature_key)"
                " VALUES (:id, :bid, 'online_ordering')"
            ),
            {"id": str(uuid.uuid4()), "bid": str(business_id)},
        )


def _seed_ordering_business(
    client: TestClient,
    engine: Engine,
    create_user: CreateUser,
    create_business: CreateBusiness,
    create_membership: CreateMembership,
    *,
    slug: str = "shalik",
    owner_email: str = OWNER,
    max_orders_per_slot: int | None = None,
) -> tuple[uuid.UUID, str, str]:
    """An active, entitled, pickup-enabled business with one 1250-minor
    item; returns (business_id, item_id, owner csrf)."""
    business_id = create_business(slug, status="active")
    create_membership(business_id, create_user(owner_email), role="owner")
    _grant_online_ordering(engine, business_id)
    csrf = login_as(client, owner_email)
    base = f"/api/v1/businesses/{business_id}"
    assert (
        client.put(
            f"{base}/hours/weekly",
            json={"intervals": ALWAYS_OPEN},
            headers=csrf_headers(csrf),
        ).status_code
        == 200
    )
    fulfillment: dict[str, Any] = {
        "pickup_enabled": True,
        "asap_enabled": True,
        "lead_time_minutes": 0,
        "slot_interval_minutes": 15,
        "last_order_before_close_minutes": 0,
        "max_days_ahead": 3,
    }
    if max_orders_per_slot is not None:
        fulfillment["max_orders_per_slot"] = max_orders_per_slot
    assert (
        client.put(
            f"{base}/hours/fulfillment",
            json=fulfillment,
            headers=csrf_headers(csrf),
        ).status_code
        == 200
    )
    category = client.post(
        f"{base}/catalog/categories", json={"name": "Mains"}, headers=csrf_headers(csrf)
    )
    assert category.status_code == 201, category.text
    item = client.post(
        f"{base}/catalog/categories/{category.json()['id']}/items",
        json={"name": "Clay-oven lamb", "price_minor": 1250},
        headers=csrf_headers(csrf),
    )
    assert item.status_code == 201, item.text
    return business_id, item.json()["id"], csrf


def _place(client: TestClient, payload: dict[str, Any], host: str = "shalik.localhost") -> Any:
    return client.post(_ORDERS, json=payload, headers=_public_headers(host))


def _count(engine: Engine, table: str, business_id: uuid.UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE business_id = :bid"),  # noqa: S608
                {"bid": str(business_id)},
            ).scalar_one()
        )


class TestPlacement:
    def test_happy_path_creates_the_full_transactional_record(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        response = _place(client, _payload(item_id))
        assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["tracking_token"] != ""
        order = body["order"]
        # The exact public shape — and no customer PII, ever (review
        # amendment): the projection is share-safe by construction.
        assert set(order) == {
            "business",
            "order_number",
            "status",
            "placed_at",
            "business_timezone",
            "pickup_kind",
            "promised_pickup_at",
            # M7A (ADR-027 D7): the kitchen's estimate rides the public
            # projection (null until a member sets it).
            "estimated_ready_at",
            "currency",
            "subtotal_minor",
            "tax_minor",
            "total_minor",
            "lines",
        }
        assert order["order_number"] == 1
        assert order["status"] == "submitted"
        assert order["business_timezone"] == "America/New_York"
        assert order["currency"] == "USD"
        assert order["subtotal_minor"] == 2500
        assert order["tax_minor"] == 0
        assert order["total_minor"] == 2500
        assert order["lines"] == [
            {
                "display_name": "Clay-oven lamb",
                "quantity": 2,
                "base_price_minor": 1250,
                "options": [],
                "line_total_minor": 2500,
            }
        ]
        # One transaction, all rows durable together (§14.1).
        assert _count(migrated_engine, "orders", business_id) == 1
        assert _count(migrated_engine, "order_lines", business_id) == 1
        assert _count(migrated_engine, "order_status_events", business_id) == 1
        assert _count(migrated_engine, "idempotency_keys", business_id) == 1
        assert _count(migrated_engine, "outbox_messages", business_id) == 1
        with migrated_engine.connect() as connection:
            outbox = connection.execute(
                text("SELECT topic, status, payload::text FROM outbox_messages")
            ).one()
            assert outbox.topic == "order.placed"
            assert outbox.status == "pending"
            # Ids and facts only — the payload never carries PII.
            assert "Amina" not in outbox[2]
            event = connection.execute(
                text("SELECT from_status, to_status, actor_kind FROM order_status_events")
            ).one()
            assert (event.from_status, event.to_status, event.actor_kind) == (
                None,
                "submitted",
                "customer",
            )
            stored = connection.execute(
                text(
                    "SELECT consent_updates, consent_marketing, customer_name,"
                    " tracking_token_digest FROM orders"
                )
            ).one()
            assert (stored.consent_updates, stored.consent_marketing) == (True, False)
            assert stored.customer_name == "Amina Rahman"
            # The digest is stored; the token itself never is (ruling D4).
            assert stored.tracking_token_digest != body["tracking_token"]
            assert len(stored.tracking_token_digest) == 64

    def test_audit_records_the_placement_without_pii(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        token = _place(client, _payload(item_id)).json()["tracking_token"]
        with migrated_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT actor_user_id, details::text FROM audit_events"
                    " WHERE action = 'order.placed'"
                )
            ).one()
        assert row.actor_user_id is None  # a guest event, structurally
        assert '"order_number": 1' in row[1] or '"order_number":1' in row[1]
        assert "Amina" not in row[1]
        assert "555-0142" not in row[1]
        assert token not in row[1]

    def test_options_are_validated_and_snapshotted(
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
        base = f"/api/v1/businesses/{business_id}/catalog"
        group = client.post(
            f"{base}/items/{item_id}/modifier-groups",
            json={"name": "Spice", "min_select": 1, "max_select": 1},
            headers=csrf_headers(csrf),
        )
        assert group.status_code == 201, group.text
        option = client.post(
            f"{base}/modifier-groups/{group.json()['id']}/options",
            json={"name": "Hot", "price_delta_minor": 150},
            headers=csrf_headers(csrf),
        )
        assert option.status_code == 201, option.text
        # The options command returns the parent group view.
        option_id = option.json()["options"][0]["id"]

        # Required group unmet → cart_stale (selection_rule).
        unmet = _place(client, _payload(item_id))
        assert unmet.status_code == 409
        assert unmet.json()["error"]["code"] == "cart_stale"

        placed = _place(
            client,
            _payload(
                item_id,
                lines=[{"item_id": item_id, "quantity": 2, "option_ids": [option_id]}],
                expected_total_minor=2800,
            ),
        )
        assert placed.status_code == 201, placed.text
        line = placed.json()["order"]["lines"][0]
        assert line["options"] == [
            {"group_name": "Spice", "option_name": "Hot", "price_delta_minor": 150}
        ]
        assert line["line_total_minor"] == (1250 + 150) * 2


class TestIdempotency:
    def test_replay_returns_the_same_order_once(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        payload = _payload(item_id)
        first = _place(client, payload)
        assert first.status_code == 201
        replay = _place(client, payload)
        assert replay.status_code == 200
        assert replay.json()["order"]["order_number"] == 1
        # The token is disclosed exactly once, at creation (ruling D4).
        assert first.json()["tracking_token"] != ""
        assert replay.json()["tracking_token"] == ""
        assert _count(migrated_engine, "orders", business_id) == 1
        assert _count(migrated_engine, "outbox_messages", business_id) == 1

    def test_key_reuse_with_a_different_cart_is_a_typed_409(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        payload = _payload(item_id)
        assert _place(client, payload).status_code == 201
        reused = _place(
            client,
            {
                **payload,
                "lines": [{"item_id": item_id, "quantity": 1}],
                "expected_total_minor": 1250,
            },
        )
        assert reused.status_code == 409
        assert reused.json()["error"]["code"] == "idempotency_key_reused"
        assert _count(migrated_engine, "orders", business_id) == 1


class TestAuthoritativeTotals:
    def test_price_changed_is_a_typed_409_with_the_real_totals(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        response = _place(client, _payload(item_id, expected_total_minor=1))
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "price_changed"
        assert error["details"]["total_minor"] == 2500
        assert error["details"]["expected_total_minor"] == 1
        assert _count(migrated_engine, "orders", business_id) == 0

    def test_stale_menu_state_fails_gracefully_with_named_problems(
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
        # Sell the item out through the real availability command.
        sold_out = client.post(
            f"/api/v1/businesses/{business_id}/catalog/items/{item_id}/availability",
            json={"is_available": False},
            headers=csrf_headers(csrf),
        )
        assert sold_out.status_code == 200, sold_out.text
        response = _place(
            client,
            _payload(
                item_id,
                lines=[
                    {"item_id": item_id, "quantity": 1},
                    {"item_id": str(uuid.uuid4()), "quantity": 1},
                ],
                expected_total_minor=1250,
            ),
        )
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "cart_stale"
        assert error["details"]["problems"] == [
            {"reason": "item_unavailable", "line_index": 0, "item_id": item_id},
            {
                "reason": "item_unknown",
                "line_index": 1,
                "item_id": response.json()["error"]["details"]["problems"][1]["item_id"],
            },
        ]
        assert _count(migrated_engine, "orders", business_id) == 0


class TestPickupAndThrottle:
    def test_scheduled_pickup_accepts_a_valid_grid_slot(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        slot = _grid_slot()
        response = _place(
            client,
            _payload(
                item_id,
                pickup_kind="scheduled",
                requested_pickup_at=slot.isoformat(),
            ),
        )
        assert response.status_code == 201, response.text
        promised = datetime.fromisoformat(response.json()["order"]["promised_pickup_at"])
        assert promised == slot

    def test_an_off_grid_or_past_instant_is_slot_unavailable(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        for instant in (
            _grid_slot() + timedelta(minutes=7),  # off the grid
            datetime.now(UTC) - timedelta(days=1),  # the past
        ):
            response = _place(
                client,
                _payload(
                    item_id,
                    pickup_kind="scheduled",
                    requested_pickup_at=instant.isoformat(),
                ),
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "slot_unavailable"

    def test_the_slot_cap_counts_non_cancelled_orders(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _ = _seed_ordering_business(
            client,
            migrated_engine,
            create_user,
            create_business,
            create_membership,
            max_orders_per_slot=1,
        )
        slot = _grid_slot(offset_slots=3)
        first = _place(
            client,
            _payload(item_id, pickup_kind="scheduled", requested_pickup_at=slot.isoformat()),
        )
        assert first.status_code == 201, first.text
        second = _place(
            client,
            _payload(item_id, pickup_kind="scheduled", requested_pickup_at=slot.isoformat()),
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "slot_unavailable"
        # A cancelled order releases its slot (ruling D3: the count is
        # non-cancelled). M6B delivers the customer path; the state is
        # legal today, so it is exercised directly.
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE orders SET status = 'cancelled' WHERE business_id = :bid"),
                {"bid": str(business_id)},
            )
        third = _place(
            client,
            _payload(item_id, pickup_kind="scheduled", requested_pickup_at=slot.isoformat()),
        )
        assert third.status_code == 201, third.text

    def test_asap_refused_when_disabled_or_unschedulable(
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
        assert (
            client.put(
                f"/api/v1/businesses/{business_id}/hours/fulfillment",
                json={
                    "pickup_enabled": True,
                    "asap_enabled": False,
                    "lead_time_minutes": 0,
                    "slot_interval_minutes": 15,
                    "last_order_before_close_minutes": 0,
                    "max_days_ahead": 3,
                },
                headers=csrf_headers(csrf),
            ).status_code
            == 200
        )
        response = _place(client, _payload(item_id))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "slot_unavailable"


class TestNeutralityAndBrowserContext:
    def _assert_neutral_404(self, response: Any) -> None:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert response.headers["cache-control"] == "no-store"

    def test_unknown_and_non_active_hosts_are_neutral_404(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        payload = _payload(str(uuid.uuid4()))
        self._assert_neutral_404(_place(client, payload, host="nope.localhost"))
        for state in ("provisioning", "suspended", "closed"):
            create_business(f"biz-{state}", status=state)
            self._assert_neutral_404(_place(client, payload, host=f"biz-{state}.localhost"))

    def test_missing_entitlement_and_disabled_pickup_are_the_same_404(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # Active business, hours configured, pickup on — but no
        # online_ordering entitlement (ruling D10).
        business_id = create_business("noent", status="active")
        create_membership(business_id, create_user("noent@example.com"), role="owner")
        csrf = login_as(client, "noent@example.com")
        assert (
            client.put(
                f"/api/v1/businesses/{business_id}/hours/fulfillment",
                json={
                    "pickup_enabled": True,
                    "asap_enabled": True,
                    "lead_time_minutes": 0,
                    "slot_interval_minutes": 15,
                    "last_order_before_close_minutes": 0,
                    "max_days_ahead": 3,
                },
                headers=csrf_headers(csrf),
            ).status_code
            == 200
        )
        self._assert_neutral_404(
            _place(client, _payload(str(uuid.uuid4())), host="noent.localhost")
        )
        # Entitled but pickup disabled (the registry default) — same 404.
        business2 = create_business("nopickup", status="active")
        _grant_online_ordering(migrated_engine, business2)
        self._assert_neutral_404(
            _place(client, _payload(str(uuid.uuid4())), host="nopickup.localhost")
        )

    def test_the_post_requires_browser_context_evidence(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        payload = _payload(item_id)
        naked = client.post(_ORDERS, json=payload, headers={"host": "shalik.localhost"})
        assert naked.status_code == 403
        assert naked.json()["error"]["code"] == "csrf_rejected"
        cross = client.post(
            _ORDERS,
            json=payload,
            headers={"host": "shalik.localhost", "sec-fetch-site": "cross-site"},
        )
        assert cross.status_code == 403
        foreign_origin = client.post(
            _ORDERS,
            json=payload,
            headers={"host": "shalik.localhost", "origin": "http://other.localhost"},
        )
        assert foreign_origin.status_code == 403

    def test_the_tenant_self_origin_is_accepted(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # D9: the tenant page posting to its own origin, on a legacy
        # browser without Sec-Fetch-Site.
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        response = client.post(
            _ORDERS,
            json=_payload(item_id),
            headers={"host": "shalik.localhost", "origin": "http://shalik.localhost"},
        )
        assert response.status_code == 201, response.text


class TestTracking:
    def test_token_plus_host_reads_the_pii_free_projection(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        placed = _place(client, _payload(item_id))
        token = placed.json()["tracking_token"]
        response = client.get(f"{_ORDERS}/{token}", headers={"host": "shalik.localhost"})
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["order_number"] == 1
        assert body["status"] == "submitted"
        # The share-safe shape (review amendment): no customer fields,
        # and the token itself is never echoed back.
        assert "customer_name" not in body
        assert token not in response.text

    def test_wrong_foreign_and_malformed_tokens_are_one_neutral_404(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_a, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        _seed_ordering_business(
            client,
            migrated_engine,
            create_user,
            create_business,
            create_membership,
            slug="tandoor",
            owner_email="owner-b@example.com",
        )
        token = _place(client, _payload(item_a)).json()["tracking_token"]
        for candidate, host in (
            ("not-a-real-token", "shalik.localhost"),
            (token, "tandoor.localhost"),  # right token, wrong tenant Host
            ("x", "shalik.localhost"),  # trivially short, still one 404
        ):
            response = client.get(f"{_ORDERS}/{candidate}", headers={"host": host})
            assert response.status_code == 404, (candidate, host)
            assert response.json()["error"]["code"] == "not_found"

    def test_tracking_survives_entitlement_revocation(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # D10 as amended in review: an order already placed is a fact the
        # customer must be able to follow after ordering is switched off.
        business_id, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        token = _place(client, _payload(item_id)).json()["tracking_token"]
        with migrated_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM feature_entitlements WHERE business_id = :bid"),
                {"bid": str(business_id)},
            )
        # Placement is now the neutral 404 …
        assert _place(client, _payload(item_id)).status_code == 404
        # … while tracking and cancellation keep working by possession.
        assert (
            client.get(f"{_ORDERS}/{token}", headers={"host": "shalik.localhost"}).status_code
            == 200
        )
        cancelled = client.post(f"{_ORDERS}/{token}/cancel", headers=_public_headers())
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"


class TestCancellation:
    def test_customer_cancels_a_submitted_order_once(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        token = _place(client, _payload(item_id)).json()["tracking_token"]
        first = client.post(f"{_ORDERS}/{token}/cancel", headers=_public_headers())
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "cancelled"
        # Idempotent on repeat: same answer, no second event, no second
        # audit row — a double-tap is not an error (ruling D11).
        second = client.post(f"{_ORDERS}/{token}/cancel", headers=_public_headers())
        assert second.status_code == 200
        assert second.json()["status"] == "cancelled"
        assert _count(migrated_engine, "order_status_events", business_id) == 2
        with migrated_engine.connect() as connection:
            events = connection.execute(
                text(
                    "SELECT from_status, to_status, actor_kind FROM order_status_events"
                    " ORDER BY occurred_at, from_status NULLS FIRST"
                )
            ).all()
            audits = connection.execute(
                text(
                    "SELECT actor_user_id, details::text FROM audit_events"
                    " WHERE action = 'order.cancelled_by_customer'"
                )
            ).all()
        assert [(e.from_status, e.to_status, e.actor_kind) for e in events] == [
            (None, "submitted", "customer"),
            ("submitted", "cancelled", "customer"),
        ]
        assert len(audits) == 1
        assert audits[0].actor_user_id is None
        assert "Amina" not in audits[0][1]

    def test_cancel_requires_browser_context(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        token = _place(client, _payload(item_id)).json()["tracking_token"]
        naked = client.post(f"{_ORDERS}/{token}/cancel", headers={"host": "shalik.localhost"})
        assert naked.status_code == 403
        assert naked.json()["error"]["code"] == "csrf_rejected"

    def test_past_submitted_refuses_with_invalid_state(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # The accepted state is M7's to produce; it is legal in the DB
        # today, so the refusal is exercised directly.
        business_id, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        token = _place(client, _payload(item_id)).json()["tracking_token"]
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE orders SET status = 'accepted' WHERE business_id = :bid"),
                {"bid": str(business_id)},
            )
        response = client.post(f"{_ORDERS}/{token}/cancel", headers=_public_headers())
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state"

    def test_unknown_token_is_neutral_404(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        response = client.post(f"{_ORDERS}/never-issued/cancel", headers=_public_headers())
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestPickupSlotListing:
    def test_slots_are_bounded_sorted_future_instants(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_id, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        response = client.get("/api/v1/public/pickup-slots", headers={"host": "shalik.localhost"})
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        slots = [datetime.fromisoformat(value) for value in response.json()["slots"]]
        assert 0 < len(slots) <= 100
        assert slots == sorted(slots)
        # Lead time is zero in the fixture; every slot is current or later.
        assert slots[0] >= datetime.now(UTC) - timedelta(minutes=15)
        # A listed slot is a placeable slot (the shared bound, §5) — the
        # third listed instant is comfortably clear of the boundary the
        # clock is walking over.
        placed = _place(
            client,
            _payload(
                item_id,
                pickup_kind="scheduled",
                requested_pickup_at=slots[2].isoformat(),
            ),
        )
        assert placed.status_code == 201, placed.text

    def test_ineligible_hosts_are_neutral_404(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        # Entitled but pickup disabled; and pickup on but unentitled —
        # the same neutral 404 as an unknown host (ruling D10).
        business_id = create_business("noent2", status="active")
        create_membership(business_id, create_user("noent2@example.com"), role="owner")
        csrf = login_as(client, "noent2@example.com")
        assert (
            client.put(
                f"/api/v1/businesses/{business_id}/hours/fulfillment",
                json={
                    "pickup_enabled": True,
                    "asap_enabled": True,
                    "lead_time_minutes": 0,
                    "slot_interval_minutes": 15,
                    "last_order_before_close_minutes": 0,
                    "max_days_ahead": 3,
                },
                headers=csrf_headers(csrf),
            ).status_code
            == 200
        )
        for host in ("noent2.localhost", "nope.localhost"):
            response = client.get("/api/v1/public/pickup-slots", headers={"host": host})
            assert response.status_code == 404, host


class TestIsolation:
    def test_numbering_and_carts_do_not_cross_tenants(
        self,
        client: TestClient,
        migrated_engine: Engine,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        _, item_a, _ = _seed_ordering_business(
            client, migrated_engine, create_user, create_business, create_membership
        )
        _, item_b, _ = _seed_ordering_business(
            client,
            migrated_engine,
            create_user,
            create_business,
            create_membership,
            slug="tandoor",
            owner_email="owner-b@example.com",
        )
        first_a = _place(client, _payload(item_a))
        assert first_a.status_code == 201
        # Tenant B's first order is number 1 — sequences are per business.
        first_b = _place(client, _payload(item_b), host="tandoor.localhost")
        assert first_b.status_code == 201
        assert first_b.json()["order"]["order_number"] == 1
        # Tenant A's item under tenant B's host is an unknown line — one
        # indistinguishable answer, no cross-tenant existence disclosure.
        crossed = _place(client, _payload(item_a), host="tandoor.localhost")
        assert crossed.status_code == 409
        problems = crossed.json()["error"]["details"]["problems"]
        assert [p["reason"] for p in problems] == ["item_unknown"]
