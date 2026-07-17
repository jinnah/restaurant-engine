"""Host normalization parser (M2C, ADR-013).

Fail-closed: every malformed or ambiguous value must normalize to ``None``.
Only a valid DNS hostname yields labels; IP literals are flagged.
"""

import pytest

from app.core.hosts import normalize_host


class TestValidDnsHosts:
    def test_lowercases_and_splits_labels(self) -> None:
        result = normalize_host("Shalik.LOCALHOST")
        assert result is not None
        assert result.is_ip is False
        assert result.labels == ("shalik", "localhost")
        assert result.hostname == "shalik.localhost"

    def test_strips_port(self) -> None:
        result = normalize_host("shalik.localhost:8000")
        assert result is not None
        assert result.labels == ("shalik", "localhost")

    def test_strips_single_trailing_root_dot(self) -> None:
        result = normalize_host("shalik.localhost.")
        assert result is not None
        assert result.labels == ("shalik", "localhost")

    def test_multi_label_platform_domain(self) -> None:
        result = normalize_host("shalik.platform-domain.com")
        assert result is not None
        assert result.labels == ("shalik", "platform-domain", "com")

    def test_bare_single_label(self) -> None:
        result = normalize_host("localhost")
        assert result is not None
        assert result.is_ip is False
        assert result.labels == ("localhost",)

    def test_idna_punycode_conversion(self) -> None:
        # A non-ASCII label is converted to its ASCII (punycode) form.
        result = normalize_host("münchen.localhost")
        assert result is not None
        assert result.is_ip is False
        assert result.labels[0].startswith("xn--")
        assert result.labels[1] == "localhost"


class TestIpLiterals:
    def test_ipv4_literal_flagged(self) -> None:
        result = normalize_host("127.0.0.1")
        assert result is not None
        assert result.is_ip is True
        assert result.labels == ()

    def test_ipv4_literal_with_port(self) -> None:
        result = normalize_host("127.0.0.1:8000")
        assert result is not None
        assert result.is_ip is True

    def test_bracketed_ipv6_literal(self) -> None:
        result = normalize_host("[::1]")
        assert result is not None
        assert result.is_ip is True

    def test_bracketed_ipv6_with_port(self) -> None:
        result = normalize_host("[2001:db8::1]:8443")
        assert result is not None
        assert result.is_ip is True

    def test_bare_ipv6_is_ambiguous_and_rejected(self) -> None:
        assert normalize_host("::1") is None
        assert normalize_host("2001:db8::1") is None

    def test_malformed_bracketed_ipv6(self) -> None:
        assert normalize_host("[::1") is None
        assert normalize_host("[not-an-ip]") is None
        assert normalize_host("[::1]junk") is None


class TestRejected:
    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            " ",
            "exa mple.com",
            "example.com\n",
            "example.com\t",
            "a.com,b.com",
            "user@example.com",
            "example.com:",
            "example.com:0",
            "example.com:99999",
            "example.com:80a",
            "example.com..",
            "example.com...",
            ".example.com",
            "a..b.com",
            "-bad.com",
            "bad-.com",
            "exa_mple.com",
            ".",
        ],
    )
    def test_invalid_inputs_fail_closed(self, raw: str | None) -> None:
        assert normalize_host(raw) is None

    def test_oversized_label_rejected(self) -> None:
        assert normalize_host("a" * 64 + ".com") is None

    def test_max_label_length_allowed(self) -> None:
        result = normalize_host("a" * 63 + ".com")
        assert result is not None

    def test_oversized_total_hostname_rejected(self) -> None:
        host = ".".join(["a" * 60] * 5)  # 5*60 + 4 dots = 304 > 253
        assert normalize_host(host) is None
