"""The fail-closed browser-context check, including D9 (M6A, ADR-026).

The delivered ADR-010 branches are pinned first — Sec-Fetch-Site wins
outright, the static allowlist stands, absence of evidence rejects — and
then the M6A extension: an Origin (or Referer) whose host equals the
request's own Host is same-origin evidence for tenant hosts the static
allowlist cannot enumerate. Review deliberately rejected a broader
"tenant host family" rule, and the cross-tenant case is asserted here as
a rejection, not an acceptance.
"""

from dataclasses import dataclass, field

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from app.core.browser_context import check_browser_context
from app.core.errors import ApiError

TRUSTED = "http://testserver"


@dataclass
class _Settings:
    trusted_origin_set: set[str] = field(default_factory=lambda: {TRUSTED})


def _request(headers: dict[str, str]) -> Request:
    app = Starlette()
    app.state.settings = _Settings()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/public/orders",
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers.items()
        ],
        "app": app,
    }
    return Request(scope)


def _rejects(headers: dict[str, str]) -> None:
    with pytest.raises(ApiError) as excinfo:
        check_browser_context(_request(headers))
    assert excinfo.value.status_code == 403


class TestDeliveredBranches:
    def test_sec_fetch_same_origin_passes(self) -> None:
        check_browser_context(_request({"sec-fetch-site": "same-origin"}))

    def test_sec_fetch_cross_site_rejects_even_with_trusted_origin(self) -> None:
        # Sec-Fetch-Site is authoritative when present: a cross-site
        # verdict is final and no other evidence is consulted.
        _rejects({"sec-fetch-site": "cross-site", "origin": TRUSTED})

    def test_allowlisted_origin_passes(self) -> None:
        check_browser_context(_request({"origin": TRUSTED}))

    def test_unknown_origin_rejects(self) -> None:
        _rejects({"origin": "http://evil.example", "host": "testserver"})

    def test_no_evidence_rejects(self) -> None:
        _rejects({})


class TestSelfOriginExtension:
    """ADR-026 D9: Origin host == request Host is same-origin evidence."""

    def test_tenant_self_origin_passes(self) -> None:
        check_browser_context(
            _request({"origin": "http://shalik.localhost", "host": "shalik.localhost"})
        )

    def test_tenant_self_origin_with_port_passes(self) -> None:
        check_browser_context(
            _request({"origin": "http://shalik.localhost:3100", "host": "shalik.localhost:3100"})
        )

    def test_port_mismatch_rejects(self) -> None:
        # host:port comparison is exact — a different port is a different
        # origin, and the M8 proxy decision owns anything subtler.
        _rejects({"origin": "http://shalik.localhost:9999", "host": "shalik.localhost:3100"})

    def test_cross_tenant_origin_rejects(self) -> None:
        # The reviewed refinement: one tenant's origin must never satisfy
        # the check for another tenant's host (the "family rule" failure).
        _rejects({"origin": "http://other.localhost", "host": "shalik.localhost"})

    def test_case_is_normalized(self) -> None:
        check_browser_context(
            _request({"origin": "http://SHALIK.localhost", "host": "shalik.LOCALHOST"})
        )

    def test_self_origin_referer_passes_without_origin(self) -> None:
        check_browser_context(
            _request({"referer": "http://shalik.localhost/order", "host": "shalik.localhost"})
        )

    def test_cross_tenant_referer_rejects(self) -> None:
        _rejects({"referer": "http://other.localhost/order", "host": "shalik.localhost"})

    def test_missing_host_header_rejects_self_origin(self) -> None:
        # No request Host means no self to compare against; fail closed.
        _rejects({"origin": "http://shalik.localhost"})
