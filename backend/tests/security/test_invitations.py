"""Membership invitations (M2D, ADR-014): lifecycle, role ceiling,
isolation, two-phase acceptance, and uniform non-disclosure.

Real PostgreSQL throughout — locks, partial uniques, and SQL-clock expiry
are the subject under test.
"""

import threading
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core import security
from tests.security.conftest import (
    BROWSER_HEADERS,
    CreateBusiness,
    CreateMembership,
    CreateUser,
    csrf_headers,
    login,
    login_as,
)

_PREVIEW = "/api/v1/invitations/preview"
_ACCEPT = "/api/v1/invitations/accept"
_ACCEPT_EXISTING = "/api/v1/invitations/accept-existing"
_NEW_PASSWORD = "a brand new pw for tests!"
_INVALID_MESSAGE = "Invitation is not valid or has expired."

OWNER = "owner@example.com"
MANAGER = "manager@example.com"
STAFF = "staff@example.com"
INVITEE = "invitee@example.com"
ADMIN = "admin@example.com"


def _business_invite_url(business_id: uuid.UUID) -> str:
    return f"/api/v1/businesses/{business_id}/invitations"


def _platform_invite_url(business_id: uuid.UUID) -> str:
    return f"/api/v1/platform/businesses/{business_id}/invitations"


def _issue(
    client: TestClient,
    csrf: str,
    business_id: uuid.UUID,
    *,
    email: str = INVITEE,
    role: str = "staff",
    platform: bool = False,
) -> Any:
    url = _platform_invite_url(business_id) if platform else _business_invite_url(business_id)
    return client.post(url, json={"email": email, "role": role}, headers=csrf_headers(csrf))


def _accept(client: TestClient, token: str, *, display_name: str = "New Member") -> Any:
    return client.post(
        _ACCEPT,
        json={"token": token, "display_name": display_name, "password": _NEW_PASSWORD},
        headers=BROWSER_HEADERS,
    )


@pytest.fixture
def active_business(
    create_business: CreateBusiness,
    create_user: CreateUser,
    create_membership: CreateMembership,
) -> uuid.UUID:
    """An active business with an owner, a manager, and a staff member."""
    business_id = create_business("shalik", name="Shalik", status="active")
    create_membership(business_id, create_user(OWNER), role="owner")
    create_membership(business_id, create_user(MANAGER), role="manager")
    create_membership(business_id, create_user(STAFF), role="staff")
    return business_id


class TestIssuance:
    def test_owner_issues_and_token_is_stored_hashed(
        self,
        client: TestClient,
        active_business: uuid.UUID,
        migrated_engine: Engine,
    ) -> None:
        csrf = login_as(client, OWNER)
        response = _issue(client, csrf, active_business, role="manager")
        assert response.status_code == 201, response.text
        body = response.json()
        assert set(body) == {"token", "invitation_id", "expires_at", "email", "role"}
        assert body["email"] == INVITEE
        assert body["role"] == "manager"
        with migrated_engine.connect() as connection:
            stored = connection.execute(
                text("SELECT token_hash FROM business_invitations")
            ).scalar_one()
        assert stored == security.hash_opaque_token(body["token"])

    def test_manager_can_issue_staff_but_not_owner(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        csrf = login_as(client, MANAGER)
        assert _issue(client, csrf, active_business, role="staff").status_code == 201
        denied = _issue(client, csrf, active_business, email="second@example.com", role="owner")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "permission_denied"

    def test_staff_cannot_issue(self, client: TestClient, active_business: uuid.UUID) -> None:
        csrf = login_as(client, STAFF)
        assert _issue(client, csrf, active_business).status_code == 403

    def test_platform_admin_issues_owner_via_platform_route(
        self, client: TestClient, create_user: CreateUser, create_business: CreateBusiness
    ) -> None:
        business_id = create_business("juniper", name="Juniper")  # provisioning
        create_user(ADMIN, is_platform_admin=True)
        csrf = login_as(client, ADMIN)
        response = _issue(client, csrf, business_id, role="owner", platform=True)
        assert response.status_code == 201

    def test_platform_admin_is_a_nonmember_on_the_business_route(
        self, client: TestClient, create_user: CreateUser, active_business: uuid.UUID
    ) -> None:
        create_user(ADMIN, is_platform_admin=True)
        csrf = login_as(client, ADMIN)
        assert _issue(client, csrf, active_business).status_code == 404

    def test_already_member_email_is_409(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        csrf = login_as(client, OWNER)
        response = _issue(client, csrf, active_business, email=STAFF)
        assert response.status_code == 409

    def test_issuance_does_not_disclose_account_existence(
        self, client: TestClient, active_business: uuid.UUID, create_user: CreateUser
    ) -> None:
        # One invitee has an account, the other does not; the issuer sees
        # identical response shapes either way.
        create_user("registered@example.com")
        csrf = login_as(client, OWNER)
        with_account = _issue(client, csrf, active_business, email="registered@example.com")
        without_account = _issue(client, csrf, active_business, email="fresh@example.com")
        assert with_account.status_code == without_account.status_code == 201
        assert set(with_account.json()) == set(without_account.json())

    def test_suspended_business_cannot_issue(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        create_membership: CreateMembership,
    ) -> None:
        business_id = create_business("paused", name="Paused", status="suspended")
        create_membership(business_id, create_user(OWNER), role="owner")
        csrf = login_as(client, OWNER)
        response = _issue(client, csrf, business_id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state"

    def test_reissue_replaces_and_revokes_predecessor(
        self, client: TestClient, active_business: uuid.UUID, migrated_engine: Engine
    ) -> None:
        csrf = login_as(client, OWNER)
        first = _issue(client, csrf, active_business).json()["token"]
        second = _issue(client, csrf, active_business).json()["token"]
        # Old token dead, new token lives; exactly one pending row remains.
        preview_old = client.post(_PREVIEW, json={"token": first}, headers=BROWSER_HEADERS)
        preview_new = client.post(_PREVIEW, json={"token": second}, headers=BROWSER_HEADERS)
        assert preview_old.status_code == 404
        assert preview_new.status_code == 200
        with migrated_engine.connect() as connection:
            pending = connection.execute(
                text(
                    "SELECT count(*) FROM business_invitations"
                    " WHERE accepted_at IS NULL AND revoked_at IS NULL"
                )
            ).scalar_one()
        assert pending == 1


class TestRoleCeilingOnReplaceAndRevoke:
    """Correction C: a manager cannot interfere with an owner invitation."""

    def test_manager_cannot_replace_an_owner_invitation(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        owner_csrf = login_as(client, OWNER)
        issued = _issue(client, owner_csrf, active_business, role="owner")
        assert issued.status_code == 201

        with TestClient(client.app) as manager_client:
            manager_csrf = login_as(manager_client, MANAGER)
            # Reissue against the same email with a weaker role must NOT
            # revoke the pending owner invitation.
            response = _issue(manager_client, manager_csrf, active_business, role="staff")
            assert response.status_code == 403
        # The owner invitation is still redeemable.
        preview = client.post(
            _PREVIEW, json={"token": issued.json()["token"]}, headers=BROWSER_HEADERS
        )
        assert preview.status_code == 200

    def test_manager_cannot_revoke_an_owner_invitation_but_owner_can(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        owner_csrf = login_as(client, OWNER)
        invitation_id = _issue(client, owner_csrf, active_business, role="owner").json()[
            "invitation_id"
        ]
        revoke_url = f"{_business_invite_url(active_business)}/{invitation_id}/revoke"

        with TestClient(client.app) as manager_client:
            manager_csrf = login_as(manager_client, MANAGER)
            denied = manager_client.post(revoke_url, json={}, headers=csrf_headers(manager_csrf))
            assert denied.status_code == 403

        allowed = client.post(revoke_url, json={}, headers=csrf_headers(owner_csrf))
        assert allowed.status_code == 200
        assert allowed.json() == {"status": "revoked"}

    def test_manager_can_revoke_staff_invitation(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        csrf = login_as(client, MANAGER)
        invitation_id = _issue(client, csrf, active_business, role="staff").json()["invitation_id"]
        response = client.post(
            f"{_business_invite_url(active_business)}/{invitation_id}/revoke",
            json={},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200


class TestPreview:
    def test_preview_masks_the_email(self, client: TestClient, active_business: uuid.UUID) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        response = client.post(_PREVIEW, json={"token": token}, headers=BROWSER_HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "business_name": "Shalik",
            "role": "staff",
            "email_hint": "i***@example.com",
        }
        assert INVITEE not in str(body)

    def test_preview_is_no_store_and_invalid_is_uniform_404(self, client: TestClient) -> None:
        response = client.post(
            _PREVIEW,
            json={"token": security.generate_opaque_token()},
            headers=BROWSER_HEADERS,
        )
        assert response.status_code == 404
        assert response.json()["error"]["message"] == _INVALID_MESSAGE
        assert response.headers["cache-control"] == "no-store"


class TestAcceptanceNewUser:
    def test_full_flow_creates_user_and_membership_without_login(
        self, client: TestClient, active_business: uuid.UUID, migrated_engine: Engine
    ) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business, role="manager").json()["token"]

        with TestClient(client.app) as public:
            response = _accept(public, token)
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["status"] == "accepted"
            assert body["email"] == INVITEE
            assert body["role"] == "manager"
            # No auto-login: no session cookie was set.
            assert "set-cookie" not in response.headers
            # The account works through the normal login flow.
            assert login(public, email=INVITEE, password=_NEW_PASSWORD).status_code == 200

        with migrated_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT m.role, i.accepted_at FROM memberships m"
                    " JOIN users u ON u.id = m.user_id"
                    " JOIN business_invitations i ON i.accepted_user_id = u.id"
                    " WHERE u.email_normalized = :email"
                ),
                {"email": INVITEE},
            ).one()
        assert row.role == "manager"
        assert row.accepted_at is not None

    def test_single_use_sequential_second_accept_fails(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        assert _accept(client, token).status_code == 201
        second = _accept(client, token, display_name="Somebody Else")
        assert second.status_code == 404
        assert second.json()["error"]["message"] == _INVALID_MESSAGE

    def test_email_registered_since_issuance_is_uniform_404(
        self, client: TestClient, active_business: uuid.UUID, create_user: CreateUser
    ) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        create_user(INVITEE)  # the invitee registered some other way
        response = _accept(client, token)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == _INVALID_MESSAGE

    def test_expired_and_revoked_and_suspended_are_uniform_404(
        self,
        client: TestClient,
        active_business: uuid.UUID,
        create_business: CreateBusiness,
        create_user: CreateUser,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        owner_csrf = login_as(client, OWNER)
        # Expired: backdate a real invitation.
        expired_token = _issue(client, owner_csrf, active_business).json()["token"]
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE business_invitations SET created_at = now() - interval '9 days',"
                    " expires_at = now() - interval '2 days'"
                )
            )
        # Revoked: fresh invitation, then revoke.
        revoked = _issue(client, owner_csrf, active_business, email="r@example.com")
        client.post(
            f"{_business_invite_url(active_business)}/{revoked.json()['invitation_id']}/revoke",
            json={},
            headers=csrf_headers(owner_csrf),
        )
        # Business suspended after issuance.
        other_business = create_business("bravo", name="Bravo", status="active")
        create_membership(other_business, create_user("bravo-owner@example.com"), role="owner")
        with TestClient(client.app) as bravo_client:
            bravo_csrf = login_as(bravo_client, "bravo-owner@example.com")
            suspended_token = _issue(
                bravo_client, bravo_csrf, other_business, email="s@example.com"
            ).json()["token"]
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'suspended' WHERE id = :bid"),
                {"bid": other_business},
            )

        for raw in (expired_token, revoked.json()["token"], suspended_token):
            response = _accept(client, raw)
            assert response.status_code == 404
            assert response.json()["error"]["message"] == _INVALID_MESSAGE

    def test_accept_binds_to_the_issuing_business_only(
        self,
        client: TestClient,
        active_business: uuid.UUID,
        migrated_engine: Engine,
    ) -> None:
        """Cross-business control: acceptance creates a membership in exactly
        the inviting business."""
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        assert _accept(client, token).status_code == 201
        with migrated_engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT business_id FROM memberships m JOIN users u"
                    " ON u.id = m.user_id WHERE u.email_normalized = :email"
                ),
                {"email": INVITEE},
            ).all()
        assert [row.business_id for row in rows] == [active_business]


class TestConcurrentAcceptance:
    """Genuinely overlapping double-accept of one token (addendum requirement).

    A barrier inside ``hash_password`` — which both requests reach only
    after passing phase-1 prevalidation, at the point where no transaction
    or row lock is held (phase 1 was rolled back, phase 2 has not begun) —
    deterministically holds both requests past eligibility before either
    enters the authoritative locked phase. The ``FOR UPDATE`` + locked
    revalidation design must then let exactly one win.
    """

    def test_concurrent_double_accept_one_winner_one_neutral_404(
        self,
        client: TestClient,
        active_business: uuid.UUID,
        migrated_engine: Engine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business, role="staff").json()["token"]

        barrier = threading.Barrier(2)
        real_hash = security.hash_password

        def synchronized_hash(password: str) -> str:
            # Rendezvous between the two phases: a broken barrier (one side
            # never arrived) raises and fails the request loudly rather
            # than hanging the test.
            barrier.wait(timeout=15)
            return real_hash(password)

        monkeypatch.setattr("app.core.security.hash_password", synchronized_hash)

        responses: dict[str, Any] = {}
        failures: dict[str, Exception] = {}

        def attempt(name: str, public: TestClient) -> None:
            try:
                responses[name] = _accept(public, token, display_name=name)
            except Exception as exc:  # surfaced as a test failure below
                failures[name] = exc

        # Each request runs on its own TestClient (own portal/event loop)
        # and therefore its own request-scoped SQLAlchemy session; nothing
        # database-facing is shared between the two threads.
        with TestClient(client.app) as first, TestClient(client.app) as second:
            threads = [
                threading.Thread(target=attempt, args=("Racer One", first), daemon=True),
                threading.Thread(target=attempt, args=("Racer Two", second), daemon=True),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            assert not any(t.is_alive() for t in threads), "concurrent accepts did not finish"
        assert not failures, f"request thread raised: {failures}"
        monkeypatch.setattr("app.core.security.hash_password", real_hash)

        # Exactly one contractual success, exactly one neutral 404.
        assert sorted(r.status_code for r in responses.values()) == [201, 404], {
            name: response.text for name, response in responses.items()
        }
        winner = next(r for r in responses.values() if r.status_code == 201)
        loser = next(r for r in responses.values() if r.status_code == 404)
        assert winner.json()["status"] == "accepted"
        assert loser.json()["error"]["message"] == _INVALID_MESSAGE
        # No auto-login on either outcome.
        assert "set-cookie" not in winner.headers
        assert "set-cookie" not in loser.headers

        with migrated_engine.connect() as connection:
            users = connection.execute(
                text("SELECT id FROM users WHERE email_normalized = :email"),
                {"email": INVITEE},
            ).all()
            assert len(users) == 1, "the race must not create a duplicate account"
            user_id = users[0].id
            membership_rows = connection.execute(
                text("SELECT business_id FROM memberships WHERE user_id = :uid"),
                {"uid": user_id},
            ).all()
            assert [row.business_id for row in membership_rows] == [active_business]
            invitation = connection.execute(
                text("SELECT accepted_at, accepted_user_id FROM business_invitations")
            ).one()  # .one() doubles as the no-duplicate-invitation assertion
            assert invitation.accepted_at is not None
            assert invitation.accepted_user_id == user_id
            sessions = connection.execute(
                text("SELECT count(*) FROM sessions WHERE user_id = :uid"), {"uid": user_id}
            ).scalar_one()
            assert sessions == 0, "acceptance must never create a session"


class TestAcceptanceExistingUser:
    def test_existing_user_gains_second_membership(
        self,
        client: TestClient,
        active_business: uuid.UUID,
        create_business: CreateBusiness,
        create_user: CreateUser,
        create_membership: CreateMembership,
    ) -> None:
        # INVITEE already owns another business.
        other = create_business("theirs", name="Theirs", status="active")
        create_membership(other, create_user(INVITEE), role="owner")

        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business, role="staff").json()["token"]

        with TestClient(client.app) as invitee_client:
            invitee_csrf = login_as(invitee_client, INVITEE)
            response = invitee_client.post(
                _ACCEPT_EXISTING,
                json={"token": token},
                headers=csrf_headers(invitee_csrf),
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "accepted"
            # The session now shows both memberships.
            session = invitee_client.get("/api/v1/auth/session").json()
            slugs = sorted(m["business_slug"] for m in session["memberships"])
            assert slugs == ["shalik", "theirs"]

    def test_wrong_account_gets_uniform_404(
        self, client: TestClient, active_business: uuid.UUID, create_user: CreateUser
    ) -> None:
        create_user("somebody-else@example.com")
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        with TestClient(client.app) as other_client:
            other_csrf = login_as(other_client, "somebody-else@example.com")
            response = other_client.post(
                _ACCEPT_EXISTING, json={"token": token}, headers=csrf_headers(other_csrf)
            )
            assert response.status_code == 404
            assert response.json()["error"]["message"] == _INVALID_MESSAGE

    def test_unauthenticated_accept_existing_is_401(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        with TestClient(client.app) as anonymous:
            response = anonymous.post(
                _ACCEPT_EXISTING, json={"token": token}, headers=BROWSER_HEADERS
            )
            assert response.status_code == 401


class TestPendingList:
    def test_list_projection_has_no_token_fields(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        csrf = login_as(client, OWNER)
        _issue(client, csrf, active_business)
        body = client.get(_business_invite_url(active_business)).json()
        assert body["total"] == 1
        item = body["items"][0]
        assert set(item) == {
            "invitation_id",
            "email",
            "role",
            "created_at",
            "expires_at",
            "state",
            "invited_by_user_id",
        }
        assert item["state"] == "pending"

    def test_accepted_and_revoked_leave_the_list(
        self, client: TestClient, active_business: uuid.UUID
    ) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        _accept(client, token)
        body = client.get(_business_invite_url(active_business)).json()
        assert body["total"] == 0

    def test_staff_cannot_list(self, client: TestClient, active_business: uuid.UUID) -> None:
        login_as(client, STAFF)
        assert client.get(_business_invite_url(active_business)).status_code == 403

    def test_cross_business_isolation(
        self,
        client: TestClient,
        active_business: uuid.UUID,
        create_business: CreateBusiness,
        create_user: CreateUser,
        create_membership: CreateMembership,
    ) -> None:
        other = create_business("other", name="Other", status="active")
        create_membership(other, create_user("other-owner@example.com"), role="owner")
        csrf = login_as(client, OWNER)
        _issue(client, csrf, active_business)
        with TestClient(client.app) as other_client:
            login_as(other_client, "other-owner@example.com")
            # Their own list is empty; the Shalik list is a nonmember 404.
            assert other_client.get(_business_invite_url(other)).json()["total"] == 0
            assert other_client.get(_business_invite_url(active_business)).status_code == 404

    def test_revoke_still_works_for_suspended_business(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        create_user: CreateUser,
        create_membership: CreateMembership,
        migrated_engine: Engine,
    ) -> None:
        business_id = create_business("pausing", name="Pausing", status="active")
        create_membership(business_id, create_user(OWNER), role="owner")
        csrf = login_as(client, OWNER)
        invitation_id = _issue(client, csrf, business_id).json()["invitation_id"]
        with migrated_engine.begin() as connection:
            connection.execute(
                text("UPDATE businesses SET status = 'suspended' WHERE id = :bid"),
                {"bid": business_id},
            )
        response = client.post(
            f"{_business_invite_url(business_id)}/{invitation_id}/revoke",
            json={},
            headers=csrf_headers(csrf),
        )
        assert response.status_code == 200


class TestArgonPrevalidationForAcceptance:
    """Correction A applies to acceptance exactly as to redemption."""

    @pytest.fixture
    def hash_counter(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        calls: list[str] = []
        original = security.hash_password

        def counting(password: str) -> str:
            calls.append("hash")
            return original(password)

        monkeypatch.setattr("app.core.security.hash_password", counting)
        return calls

    def test_invalid_tokens_never_reach_argon2(
        self, client: TestClient, hash_counter: list[str]
    ) -> None:
        for _ in range(3):
            assert _accept(client, security.generate_opaque_token()).status_code == 404
        assert hash_counter == []

    def test_valid_token_hashes_exactly_once(
        self, client: TestClient, active_business: uuid.UUID, hash_counter: list[str]
    ) -> None:
        csrf = login_as(client, OWNER)
        token = _issue(client, csrf, active_business).json()["token"]
        assert _accept(client, token).status_code == 201
        assert hash_counter == ["hash"]


class TestOwnerBootstrapFlow:
    def test_platform_invites_owner_then_activation_succeeds(
        self, client: TestClient, create_user: CreateUser, create_business: CreateBusiness
    ) -> None:
        """The full M2D onboarding arc: create → invite owner → accept →
        activate (the M2B owner guard is finally satisfiable end-to-end)."""
        business_id = create_business("fresh", name="Fresh")  # provisioning
        create_user(ADMIN, is_platform_admin=True)
        csrf = login_as(client, ADMIN)

        # Activation fails while ownerless (M2B invariant intact).
        activate_url = f"/api/v1/platform/businesses/{business_id}/activate"
        assert client.post(activate_url, json={}, headers=csrf_headers(csrf)).status_code == 409

        token = _issue(client, csrf, business_id, role="owner", platform=True).json()["token"]
        with TestClient(client.app) as public:
            assert _accept(public, token, display_name="First Owner").status_code == 201

        assert client.post(activate_url, json={}, headers=csrf_headers(csrf)).status_code == 200


def test_invitation_audit_trail_has_no_tokens(
    client: TestClient, active_business: uuid.UUID, migrated_engine: Engine
) -> None:
    csrf = login_as(client, OWNER)
    issued = _issue(client, csrf, active_business)
    token = issued.json()["token"]
    _accept(client, token)
    with migrated_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT action, details::text AS details FROM audit_events"
                " WHERE action LIKE 'business.invitation%' ORDER BY id"
            )
        ).all()
    actions = [row.action for row in rows]
    assert actions == ["business.invitation_issued", "business.invitation_accepted"]
    for row in rows:
        assert token not in row.details
        assert security.hash_opaque_token(token) not in row.details


def test_raw_invitation_token_never_appears_in_logs(
    client: TestClient,
    active_business: uuid.UUID,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csrf = login_as(client, OWNER)
    token = _issue(client, csrf, active_business).json()["token"]
    assert _accept(client, token).status_code == 201
    captured = capsys.readouterr()
    assert token not in captured.out
    assert token not in captured.err
