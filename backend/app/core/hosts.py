"""Parser-level Host header normalization (M2C, ADR-013).

Fail-closed by construction: any malformed, ambiguous, or non-conforming
Host yields ``None`` (INVALID), never a best-effort guess. Only a
syntactically valid DNS hostname is normalized into labels; IP literals are
recognized and flagged (``is_ip``) so that resolution can refuse them — an
IP address or a bare single-label host is never a tenant.

The Host header is untrusted client input. This module performs input
validation and canonicalization only; it makes no claim that a Host is
authentic (ADR-013). Forwarded headers are never consulted here.
"""

import ipaddress
from dataclasses import dataclass

# RFC 1035 limits: a label is 1-63 octets; a hostname is at most 253 octets
# once the trailing root dot is removed.
_MAX_LABEL_OCTETS = 63
_MAX_HOSTNAME_OCTETS = 253

# Letters/digits/hyphen — the LDH rule. Labels are lowercased before this
# check, so only lowercase letters appear.
_LABEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


@dataclass(frozen=True)
class NormalizedHost:
    """A canonicalized Host value.

    ``labels`` are the lowercased ASCII DNS labels (empty for an IP literal).
    ``is_ip`` marks IPv4/IPv6 literals, which resolution must refuse.
    """

    hostname: str
    labels: tuple[str, ...]
    is_ip: bool


def _has_control_or_space(value: str) -> bool:
    return any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _valid_port(port: str) -> bool:
    # Must be a non-empty run of ASCII digits in 1..65535 (0 and out-of-range
    # rejected). ``str.isdigit`` also accepts some non-ASCII digit characters,
    # so the ASCII guard is deliberate.
    if not port.isascii() or not port.isdigit():
        return False
    return 1 <= int(port) <= 65535


def _normalize_label(label: str) -> str | None:
    """Canonicalize one DNS label, or ``None`` if it is not a valid label."""
    if not label.isascii():
        # IDNA/punycode conversion for internationalized labels; any failure
        # (empty, over-long, disallowed codepoint) fails closed.
        try:
            label = label.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            return None
    label = label.lower()
    if not 1 <= len(label) <= _MAX_LABEL_OCTETS:
        return None
    if label[0] == "-" or label[-1] == "-":
        return None
    if any(ch not in _LABEL_CHARS for ch in label):
        return None
    return label


def _normalize_dns(host: str) -> NormalizedHost | None:
    labels: list[str] = []
    for raw_label in host.split("."):
        if raw_label == "":  # empty label: leading dot or consecutive dots
            return None
        normalized = _normalize_label(raw_label)
        if normalized is None:
            return None
        labels.append(normalized)
    hostname = ".".join(labels)
    if len(hostname) > _MAX_HOSTNAME_OCTETS:
        return None
    return NormalizedHost(hostname=hostname, labels=tuple(labels), is_ip=False)


def _parse_bracketed_ipv6(value: str) -> NormalizedHost | None:
    end = value.find("]")
    if end == -1:  # opening bracket with no close
        return None
    inner = value[1:end]
    rest = value[end + 1 :]
    if rest != "":
        if not rest.startswith(":"):
            return None
        if not _valid_port(rest[1:]):
            return None
    try:
        address = ipaddress.IPv6Address(inner)
    except ValueError:
        return None
    return NormalizedHost(hostname=str(address), labels=(), is_ip=True)


def normalize_host(raw: str | None) -> NormalizedHost | None:
    """Normalize a raw Host header value, or ``None`` when it is invalid.

    Handles: missing/empty input; whitespace/control characters; combined
    (comma-joined) Host values; user-info-like input; ports (valid, empty,
    zero, out-of-range); one trailing root dot vs. multiple; empty and
    consecutive labels; label and total-length limits; ASCII case folding;
    IDNA/punycode conversion and failure; IPv4 literals; bracketed IPv6
    literals and malformed brackets; and bare (unbracketed) IPv6, which is
    ambiguous and rejected.
    """
    if raw is None or raw == "":
        return None
    if _has_control_or_space(raw):
        return None
    # A single Host header is required; proxies/clients that combine several
    # produce a comma-joined value — reject rather than guess.
    if "," in raw:
        return None
    # User-info ("user@host") has no place in a Host header.
    if "@" in raw:
        return None

    if raw.startswith("["):
        return _parse_bracketed_ipv6(raw)

    colon_count = raw.count(":")
    host = raw
    if colon_count == 1:
        host, _, port = raw.partition(":")
        if host == "" or not _valid_port(port):
            return None
    elif colon_count >= 2:
        # Bare (unbracketed) IPv6 is ambiguous with host:port — fail closed.
        return None

    # Exactly one trailing root dot is allowed; strip it. Two or more, or a
    # value that is only dots, is invalid.
    if host.endswith("."):
        if host.endswith(".."):
            return None
        host = host[:-1]
    if host == "":
        return None

    # An IPv4 literal is not a tenant host.
    try:
        address = ipaddress.IPv4Address(host)
    except ValueError:
        return _normalize_dns(host)
    return NormalizedHost(hostname=str(address), labels=(), is_ip=True)
