"""Feature entitlements (M2D, ADR-014): platform mutation, member reads,
fail-closed unknown keys, and cross-business isolation."""

import uuid
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

ADMIN = "admin@example.com"
OWNER = "owner@example.com"
STAFF = "staff@example.com"


def _put_url(business_id: uuid.UUID) -> str:
    return f"/api/v1/platform/businesses/{business_id}/entitlements"


def _get_url(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/entitlements"


def _set(client: TestClient, csrf: str, business_id: uuid.UUID, features: list[str]) -> Any:
    return client.put(
        _put_url(business_id), json={"features": features}, headers=csrf_headers(csrf)
    )


class TestPlatformMutation:
    def test_set_and_clear_with_audited_diff(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_user(ADMIN, is_platform_admin=True)
        csrf = login_as(client, ADMIN)

        granted = _set(client, csrf, business_id, ["online_ordering"])
        assert granted.status_code == 200, granted.text
        assert granted.json() == {"features": ["online_ordering"]}

        # Idempotent re-PUT: no new audit events.
        assert _set(client, csrf, business_id, ["online_ordering"]).status_code == 200
        cleared = _set(client, csrf, business_id, [])
        assert cleared.json() == {"features": []}

        with migrated_engine.connect() as connection:
            actions = list(
                connection.execute(
                    text(
                        "SELECT action FROM audit_events"
                        " WHERE action LIKE 'business.entitlement%' ORDER BY id"
                    )
                ).scalars()
            )
        assert actions == [
            "business.entitlement_granted",
            "business.entitlement_revoked",
        ]

    def test_unknown_requested_key_is_422(
        self, client: TestClient, create_user: CreateUser, create_business: CreateBusiness
    ) -> None:
        business_id = create_business("shalik")
        create_user(ADMIN, is_platform_admin=True)
        csrf = login_as(client, ADMIN)
        response = _set(client, csrf, business_id, ["time_travel"])
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_closed_business_is_immutable_but_suspended_is_not(
        self, client: TestClient, create_user: CreateUser, create_business: CreateBusiness
    ) -> None:
        closed = create_business("gone", status="closed")
        suspended = create_business("paused", status="suspended")
        create_user(ADMIN, is_platform_admin=True)
        csrf = login_as(client, ADMIN)
        refused = _set(client, csrf, closed, ["online_ordering"])
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "invalid_state"
        assert _set(client, csrf, suspended, ["online_ordering"]).status_code == 200

    def test_business_owner_cannot_mutate(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        csrf = login_as(client, OWNER)
        assert _set(client, csrf, business_id, ["online_ordering"]).status_code == 403

    def test_unknown_business_is_404(self, client: TestClient, create_user: CreateUser) -> None:
        create_user(ADMIN, is_platform_admin=True)
        csrf = login_as(client, ADMIN)
        assert _set(client, csrf, uuid.uuid4(), []).status_code == 404


class TestMemberRead:
    def test_members_of_any_role_can_read(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        create_membership(business_id, create_user(STAFF), role="staff")
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO feature_entitlements (id, business_id, feature_key)"
                    " VALUES (gen_random_uuid(), :bid, 'online_ordering')"
                ),
                {"bid": business_id},
            )
        for email in (OWNER, STAFF):
            with TestClient(client.app) as member_client:
                login_as(member_client, email)
                body = member_client.get(_get_url(business_id)).json()
                assert body == {"features": ["online_ordering"]}

    def test_nonmember_and_platform_admin_get_404(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_user(ADMIN, is_platform_admin=True)
        login_as(client, ADMIN)
        assert client.get(_get_url(business_id)).status_code == 404

    def test_cross_business_isolation(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        """Mutation control: if the business_id predicate were dropped from
        the entitlement lookup, business B would inherit A's features and
        this test would fail."""
        business_a = create_business("alpha", status="active")
        business_b = create_business("bravo", status="active")
        create_membership(business_b, create_user(OWNER), role="owner")
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO feature_entitlements (id, business_id, feature_key)"
                    " VALUES (gen_random_uuid(), :bid, 'online_ordering')"
                ),
                {"bid": business_a},
            )
        login_as(client, OWNER)
        assert client.get(_get_url(business_b)).json() == {"features": []}
        # And B's member cannot read A's set at all.
        assert client.get(_get_url(business_a)).status_code == 404


class TestUnknownStoredKeysFailClosed:
    def test_unknown_stored_key_is_excluded_logged_and_cleaned_up(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_business: CreateBusiness,
        create_membership: CreateMembership,
        migrated_engine: Engine,
        capsys: Any,
    ) -> None:
        business_id = create_business("shalik", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        create_user(ADMIN, is_platform_admin=True)
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO feature_entitlements (id, business_id, feature_key) VALUES"
                    " (gen_random_uuid(), :bid, 'online_ordering'),"
                    " (gen_random_uuid(), :bid, 'not_a_real_feature')"
                ),
                {"bid": business_id},
            )

        # Reads exclude the unknown key and raise the operational alarm.
        login_as(client, OWNER)
        body = client.get(_get_url(business_id)).json()
        assert body == {"features": ["online_ordering"]}
        captured = capsys.readouterr()
        assert "entitlement_unknown_key" in captured.out + captured.err

        # A full-set replacement deletes the unknown row (never legitimized).
        with TestClient(client.app) as admin_client:
            csrf = login_as(admin_client, ADMIN)
            result = _set(admin_client, csrf, business_id, ["online_ordering"])
            assert result.status_code == 200
        with migrated_engine.connect() as connection:
            keys = list(
                connection.execute(
                    text("SELECT feature_key FROM feature_entitlements ORDER BY feature_key")
                ).scalars()
            )
        assert keys == ["online_ordering"]
