"""Business lifecycle over HTTP (M2B): transitions, guards, audit.

All routes are platform-capability gated; these tests log in as a platform
admin. The owner precondition for activation is met by seeding a membership
row directly (approved point 8 — no onboarding endpoint exists yet).
"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.security.conftest import (
    CreateMembership,
    CreateUser,
    csrf_headers,
    login_as,
)

ADMIN = "admin@example.com"


def _admin_client(client: TestClient, create_user: CreateUser) -> str:
    create_user(ADMIN, is_platform_admin=True)
    return login_as(client, ADMIN)


def _create_business(client: TestClient, csrf: str, slug: str = "juniper") -> dict[str, Any]:
    response = client.post(
        "/api/v1/platform/businesses",
        json={"name": "Juniper", "slug": slug},
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _post(client: TestClient, path: str, csrf: str) -> Any:
    return client.post(path, json={}, headers=csrf_headers(csrf))


def _status(engine: Engine, business_id: str) -> str:
    with engine.connect() as connection:
        value = connection.execute(
            text("SELECT status FROM businesses WHERE id = :id"), {"id": business_id}
        ).scalar_one()
        return str(value)


def _audit_actions(engine: Engine) -> list[str]:
    """Business lifecycle audit actions only (ignores the admin's login event)."""
    with engine.connect() as connection:
        return list(
            connection.execute(
                text("SELECT action FROM audit_events WHERE action LIKE 'business.%' ORDER BY id")
            ).scalars()
        )


class TestCreate:
    def test_creates_in_provisioning_with_audit(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        csrf = _admin_client(client, create_user)
        body = _create_business(client, csrf)
        assert body["status"] == "provisioning"
        assert body["slug"] == "juniper"
        assert body["currency"] == "USD"
        assert _audit_actions(migrated_engine) == ["business.created"]

    def test_slug_is_canonicalized(self, client: TestClient, create_user: CreateUser) -> None:
        csrf = _admin_client(client, create_user)
        response = client.post(
            "/api/v1/platform/businesses",
            json={"name": "Juniper", "slug": "  JuniPer-Cafe  "},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 201
        assert response.json()["slug"] == "juniper-cafe"

    def test_duplicate_slug_is_409_conflict(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        csrf = _admin_client(client, create_user)
        _create_business(client, csrf, slug="taken")
        response = client.post(
            "/api/v1/platform/businesses",
            json={"name": "Other", "slug": "taken"},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_invalid_slug_and_timezone_are_422(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        csrf = _admin_client(client, create_user)
        assert (
            client.post(
                "/api/v1/platform/businesses",
                json={"name": "X", "slug": "-bad-"},
                headers=csrf_headers(csrf),
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/platform/businesses",
                json={"name": "X", "slug": "okay", "timezone": "Mars/Phobos"},
                headers=csrf_headers(csrf),
            ).status_code
            == 422
        )

    def test_extra_field_is_rejected(self, client: TestClient, create_user: CreateUser) -> None:
        csrf = _admin_client(client, create_user)
        response = client.post(
            "/api/v1/platform/businesses",
            json={"name": "X", "slug": "okay", "is_platform_owned": True},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422


class TestTransitions:
    def test_full_happy_path_with_audit_trail(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        csrf = _admin_client(client, create_user)
        business = _create_business(client, csrf)
        bid = business["id"]
        # Seed an owner so activation's precondition is met.
        owner_id = create_user("owner@example.com")
        create_membership(uuid.UUID(bid), owner_id, role="owner")

        assert _post(client, f"/api/v1/platform/businesses/{bid}/activate", csrf).status_code == 200
        assert _status(migrated_engine, bid) == "active"
        assert _post(client, f"/api/v1/platform/businesses/{bid}/suspend", csrf).status_code == 200
        assert _status(migrated_engine, bid) == "suspended"
        assert (
            _post(client, f"/api/v1/platform/businesses/{bid}/reactivate", csrf).status_code == 200
        )
        assert _status(migrated_engine, bid) == "active"
        assert _post(client, f"/api/v1/platform/businesses/{bid}/suspend", csrf).status_code == 200
        assert _post(client, f"/api/v1/platform/businesses/{bid}/close", csrf).status_code == 200
        assert _status(migrated_engine, bid) == "closed"

        assert _audit_actions(migrated_engine) == [
            "business.created",
            "business.activated",
            "business.suspended",
            "business.reactivated",
            "business.suspended",
            "business.closed",
        ]

    def test_activation_without_owner_is_409(
        self, client: TestClient, create_user: CreateUser, migrated_engine: Engine
    ) -> None:
        csrf = _admin_client(client, create_user)
        bid = _create_business(client, csrf)["id"]
        response = _post(client, f"/api/v1/platform/businesses/{bid}/activate", csrf)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state"
        assert _status(migrated_engine, bid) == "provisioning"

    def test_illegal_transitions_are_409(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_membership: CreateMembership,
    ) -> None:
        csrf = _admin_client(client, create_user)
        bid = _create_business(client, csrf)["id"]
        owner_id = create_user("owner@example.com")
        create_membership(uuid.UUID(bid), owner_id, role="owner")
        # provisioning cannot suspend/close/reactivate.
        for verb in ("suspend", "close", "reactivate"):
            assert (
                _post(client, f"/api/v1/platform/businesses/{bid}/{verb}", csrf).status_code == 409
            )
        # active cannot close directly (ruling 1).
        _post(client, f"/api/v1/platform/businesses/{bid}/activate", csrf)
        assert _post(client, f"/api/v1/platform/businesses/{bid}/close", csrf).status_code == 409

    def test_updated_at_increases_on_transition(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        csrf = _admin_client(client, create_user)
        bid = _create_business(client, csrf)["id"]
        owner_id = create_user("owner@example.com")
        create_membership(uuid.UUID(bid), owner_id, role="owner")

        with migrated_engine.connect() as connection:
            before = connection.execute(
                text("SELECT created_at, updated_at FROM businesses WHERE id = :id"),
                {"id": bid},
            ).one()
        _post(client, f"/api/v1/platform/businesses/{bid}/activate", csrf)
        with migrated_engine.connect() as connection:
            after = connection.execute(
                text("SELECT updated_at FROM businesses WHERE id = :id"), {"id": bid}
            ).one()
        # created_at unchanged; updated_at strictly advanced (later transaction).
        assert after.updated_at > before.updated_at
        assert after.updated_at >= before.created_at

    def test_lifecycle_command_rejects_extra_fields(
        self,
        client: TestClient,
        create_user: CreateUser,
        create_membership: CreateMembership,
    ) -> None:
        csrf = _admin_client(client, create_user)
        bid = _create_business(client, csrf)["id"]
        owner_id = create_user("owner@example.com")
        create_membership(uuid.UUID(bid), owner_id, role="owner")
        response = client.post(
            f"/api/v1/platform/businesses/{bid}/activate",
            json={"force": True},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 422

    def test_transition_on_missing_business_is_404(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        csrf = _admin_client(client, create_user)
        bid = uuid.uuid4()
        assert _post(client, f"/api/v1/platform/businesses/{bid}/suspend", csrf).status_code == 404
