"""Audit list APIs (M2D, ADR-014): authorization, tenant isolation,
cursor pagination, filter validation, and the typed safe projection.

Includes the adversarial drills required by the binding clarification:
sensitive-looking keys and nested structures inserted directly into
``audit_events.details`` must never reach a response.
"""

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.security.conftest import (
    CreateBusiness,
    CreateMembership,
    CreateUser,
    login_as,
)

_PLATFORM = "/api/v1/platform/audit-events"

ADMIN = "admin@example.com"
OWNER = "owner@example.com"
MANAGER = "manager@example.com"
STAFF = "staff@example.com"


def _business_url(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/audit-events"


def _seed_event(
    engine: Engine,
    *,
    action: str,
    business_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(
                    "INSERT INTO audit_events (occurred_at, action, business_id, details)"
                    " VALUES (now(), :action, :bid, CAST(:details AS jsonb)) RETURNING id"
                ),
                {
                    "action": action,
                    "bid": business_id,
                    "details": json.dumps(details) if details is not None else None,
                },
            ).scalar_one()
        )


class TestPlatformAuthorizationAndFilters:
    def test_requires_platform_audit_read(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        login_as(client, OWNER)
        assert client.get(_PLATFORM).status_code == 403

        with TestClient(client.app) as admin_client:
            create_user(ADMIN, is_platform_admin=True)
            login_as(admin_client, ADMIN)
            assert admin_client.get(_PLATFORM).status_code == 200

    def test_unknown_action_filter_is_422(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)
        response = client.get(_PLATFORM, params={"action": "not.a.real.action"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_registered_action_filter_works(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)  # emits auth.login_succeeded
        _seed_event(migrated_engine, action="auth.logout")
        body = client.get(_PLATFORM, params={"action": "auth.logout"}).json()
        assert [item["action"] for item in body["items"]] == ["auth.logout"]

    def test_naive_datetime_and_inverted_range_are_422(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)
        naive = client.get(_PLATFORM, params={"occurred_after": "2026-07-18T00:00:00"})
        assert naive.status_code == 422
        inverted = client.get(
            _PLATFORM,
            params={
                "occurred_after": "2026-07-18T02:00:00Z",
                "occurred_before": "2026-07-18T01:00:00Z",
            },
        )
        assert inverted.status_code == 422

    def test_limit_bounds(self, client: TestClient, create_user: CreateUser) -> None:
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)
        assert client.get(_PLATFORM, params={"limit": 101}).status_code == 422
        assert client.get(_PLATFORM, params={"limit": 0}).status_code == 422

    def test_cursor_pagination_is_exclusive_and_deterministic(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)
        seeded = [_seed_event(migrated_engine, action="auth.logout") for _ in range(5)]

        first = client.get(_PLATFORM, params={"action": "auth.logout", "limit": 2}).json()
        assert [item["id"] for item in first["items"]] == [seeded[4], seeded[3]]
        assert first["next_before_id"] == seeded[3]

        second = client.get(
            _PLATFORM,
            params={
                "action": "auth.logout",
                "limit": 2,
                "before_id": first["next_before_id"],
            },
        ).json()
        # Exclusive cursor: the boundary row is not repeated.
        assert [item["id"] for item in second["items"]] == [seeded[2], seeded[1]]

        # New events arriving between pages do not shift later pages.
        _seed_event(migrated_engine, action="auth.logout")
        third = client.get(
            _PLATFORM,
            params={
                "action": "auth.logout",
                "limit": 2,
                "before_id": second["next_before_id"],
            },
        ).json()
        assert [item["id"] for item in third["items"]] == [seeded[0]]
        assert third["next_before_id"] is None


class TestBusinessScope:
    def test_owner_and_manager_read_staff_denied_nonmember_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        create_membership(business_id, create_user(MANAGER), role="manager")
        create_membership(business_id, create_user(STAFF), role="staff")
        create_user("outsider@example.com")
        _seed_event(migrated_engine, action="business.created", business_id=business_id)

        for email, expected in ((OWNER, 200), (MANAGER, 200), (STAFF, 403)):
            with TestClient(client.app) as member_client:
                login_as(member_client, email)
                assert member_client.get(_business_url(business_id)).status_code == expected
        with TestClient(client.app) as outsider_client:
            login_as(outsider_client, "outsider@example.com")
            assert outsider_client.get(_business_url(business_id)).status_code == 404

    def test_platform_admin_is_nonmember_on_business_scope(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)
        assert client.get(_business_url(business_id)).status_code == 404

    def test_business_scope_excludes_platform_and_other_business_events(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        """Mutation controls: dropping the business_id equality would leak
        business B's rows; dropping the IS NOT NULL guard would leak
        platform/auth rows (which carry NULL business_id)."""
        business_a = create_business("alpha", status="active")
        business_b = create_business("bravo", status="active")
        create_membership(business_a, create_user(OWNER), role="owner")
        own_event = _seed_event(migrated_engine, action="business.created", business_id=business_a)
        _seed_event(migrated_engine, action="business.created", business_id=business_b)
        _seed_event(migrated_engine, action="auth.logout", business_id=None)

        login_as(client, OWNER)  # also records a NULL-business login event
        body = client.get(_business_url(business_a)).json()
        assert [item["id"] for item in body["items"]] == [own_event]
        assert all(item["business_id"] == str(business_a) for item in body["items"])


class TestSafeProjection:
    """Adversarial drills: stored JSON is never trusted."""

    def _admin(self, client: TestClient, create_user: CreateUser) -> None:
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)

    def _fetch_details(self, client: TestClient, event_id: int) -> Any:
        body = client.get(_PLATFORM, params={"limit": 100}).json()
        matches = [item for item in body["items"] if item["id"] == event_id]
        assert matches, "seeded event must appear in the page"
        return matches[0]["details"]

    def test_sensitive_keys_injected_into_details_never_return(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        self._admin(client, create_user)
        event_id = _seed_event(
            migrated_engine,
            action="business.created",
            details={
                "slug": "innocent",
                "token": "sk-super-secret",
                "password_hash": "argon2id$...",
                "authorization": "Bearer abc",
                "session_cookie": "sid=1",
            },
        )
        details = self._fetch_details(client, event_id)
        assert details == {"slug": "innocent"}
        assert "secret" not in json.dumps(details)

    def test_nested_structure_in_recognized_key_is_dropped(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        # The binding-clarification example: a recognized key carrying a
        # nested object must not be copied verbatim.
        self._admin(client, create_user)
        event_id = _seed_event(
            migrated_engine,
            action="auth.login_failed",
            details={
                "reason": {"token": "secret", "authorization": "Bearer ..."},
                "email_normalized": "a@b.co",
            },
        )
        details = self._fetch_details(client, event_id)
        assert details == {"email_normalized": "a@b.co"}
        assert "secret" not in json.dumps(details)

    def test_unregistered_action_projects_null_details(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        self._admin(client, create_user)
        event_id = _seed_event(
            migrated_engine,
            action="legacy.mystery_action",
            details={"anything": "at all", "token": "boo"},
        )
        assert self._fetch_details(client, event_id) is None

    def test_wrong_value_types_are_dropped(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        self._admin(client, create_user)
        event_id = _seed_event(
            migrated_engine,
            action="auth.login_throttled",
            details={
                "email_normalized": "a@b.co",
                "failed_login_count": "not-an-int",
                "backoff_seconds": True,  # bool is not an int here
            },
        )
        details = self._fetch_details(client, event_id)
        assert details == {"email_normalized": "a@b.co"}

    def test_oversized_string_values_are_dropped(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        self._admin(client, create_user)
        event_id = _seed_event(
            migrated_engine,
            action="business.created",
            details={"slug": "x" * 5000},
        )
        assert self._fetch_details(client, event_id) is None

    def test_business_scope_applies_the_same_projection(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        event_id = _seed_event(
            migrated_engine,
            action="business.invitation_issued",
            business_id=business_id,
            details={"email_normalized": "i@x.co", "role": "staff", "token": "leak"},
        )
        login_as(client, OWNER)
        body = client.get(_business_url(business_id)).json()
        item = next(item for item in body["items"] if item["id"] == event_id)
        assert item["details"] == {"email_normalized": "i@x.co", "role": "staff"}


def test_audit_routes_are_get_only(client: TestClient, create_user: CreateUser) -> None:
    """Immutability: the API exposes no write surface for audit events."""
    create_user(ADMIN, is_platform_admin=True)
    login_as(client, ADMIN)
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)(_PLATFORM)
        assert response.status_code == 405, method
