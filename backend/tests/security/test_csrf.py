"""Fail-closed CSRF protection (M2A, ADR-010, approved review item R2).

Layer 1: browser-context header check, exact precedence
(Sec-Fetch-Site, else Origin, else Referer, else reject).
Layer 2: the synchronizer token on cookie-authenticated unsafe requests.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.security.conftest import BROWSER_HEADERS, STANDARD_PASSWORD, CreateUser, login

LOGIN_JSON = {"email": "owner@example.com", "password": STANDARD_PASSWORD}


class TestBrowserContextPrecedence:
    """Each row of the ADR-010 precedence table, on the login endpoint."""

    def _attempt(self, client: TestClient, headers: dict[str, str]) -> int:
        response = client.post("/api/v1/auth/login", json=LOGIN_JSON, headers=headers)
        return int(response.status_code)

    def test_no_evidence_is_rejected_fail_closed(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user()
        assert self._attempt(client, {}) == 403

    def test_sec_fetch_site_same_origin_passes(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user()
        assert self._attempt(client, {"Sec-Fetch-Site": "same-origin"}) == 200

    def test_sec_fetch_site_rejections(self, client: TestClient, create_user: CreateUser) -> None:
        create_user()
        for value in ("cross-site", "same-site", "none"):
            assert self._attempt(client, {"Sec-Fetch-Site": value}) == 403, value

    def test_sec_fetch_site_wins_over_a_trusted_origin(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        # A cross-site fetch that *also* carries a trusted Origin is still
        # cross-site: precedence is part of the contract.
        create_user()
        headers = {"Sec-Fetch-Site": "cross-site", **BROWSER_HEADERS}
        assert self._attempt(client, headers) == 403

    def test_trusted_origin_passes(self, client: TestClient, create_user: CreateUser) -> None:
        create_user()
        assert self._attempt(client, BROWSER_HEADERS) == 200

    def test_untrusted_origin_is_rejected(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user()
        assert self._attempt(client, {"Origin": "https://evil.example.com"}) == 403

    def test_trusted_referer_passes_as_last_resort(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user()
        assert self._attempt(client, {"Referer": "http://testserver/login"}) == 200

    def test_untrusted_or_malformed_referer_is_rejected(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        create_user()
        assert self._attempt(client, {"Referer": "https://evil.example.com/x"}) == 403
        assert self._attempt(client, {"Referer": "not a url"}) == 403

    def test_rejection_uses_the_csrf_error_code(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/login", json=LOGIN_JSON)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_rejected"

    def test_safe_methods_need_no_browser_context(self, client: TestClient) -> None:
        # GET /session fails on authentication (401), never on CSRF (403).
        assert client.get("/api/v1/auth/session").status_code == 401


class TestSynchronizerToken:
    """Layer 2: X-CSRF-Token must match the session row (logout endpoint)."""

    def test_missing_token_is_rejected(self, client: TestClient, create_user: CreateUser) -> None:
        create_user()
        login(client)
        response = client.post("/api/v1/auth/logout", headers=BROWSER_HEADERS)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_rejected"

    def test_wrong_token_is_rejected(self, client: TestClient, create_user: CreateUser) -> None:
        create_user()
        login(client)
        response = client.post(
            "/api/v1/auth/logout",
            headers={**BROWSER_HEADERS, "X-CSRF-Token": "guessed-wrong-token"},
        )
        assert response.status_code == 403

    def test_another_sessions_token_is_rejected(
        self, app: "FastAPI", client: TestClient, create_user: CreateUser
    ) -> None:
        # CSRF tokens are per-session, not per-user: a token minted for one
        # session never authorizes another.
        create_user("alice@example.com")
        create_user("bob@example.com")
        with TestClient(app) as other_client:
            alice_csrf = login(other_client, email="alice@example.com").json()["csrf_token"]
        login(client, email="bob@example.com")
        response = client.post(
            "/api/v1/auth/logout",
            headers={**BROWSER_HEADERS, "X-CSRF-Token": alice_csrf},
        )
        assert response.status_code == 403

    def test_correct_token_passes(self, client: TestClient, create_user: CreateUser) -> None:
        create_user()
        csrf_token = login(client).json()["csrf_token"]
        response = client.post(
            "/api/v1/auth/logout",
            headers={**BROWSER_HEADERS, "X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200

    def test_token_check_runs_even_with_valid_browser_context(
        self, client: TestClient, create_user: CreateUser
    ) -> None:
        # The two layers are independent: same-origin proof does not waive
        # the synchronizer token.
        create_user()
        login(client)
        response = client.post("/api/v1/auth/logout", headers={"Sec-Fetch-Site": "same-origin"})
        assert response.status_code == 403
