"""Public media identifiers, validators, and stream cleanup (M3D, ADR-017).

Pure tests for the parts of public delivery that need neither a database
nor storage: identifier parsing, ETag derivation, conditional-request
evaluation, and the streaming generator's close guarantee.
"""

import hashlib
import uuid
from collections.abc import Generator
from typing import Any, cast

import structlog

from app.api.public_media_router import _stream_and_close
from app.domains.media import public_service
from app.domains.media.public_service import PublicRepresentation

_ASSET = uuid.UUID("11111111-2222-3333-4444-555555555555")
_CHECKSUM = "a" * 64


def _etag(variant: str = "canonical", checksum: str = _CHECKSUM) -> str:
    return public_service._derive_etag(_ASSET, variant, checksum)


class TestPublicUuidParsing:
    def test_canonical_lowercase_is_accepted(self) -> None:
        assert public_service.parse_public_uuid(str(_ASSET)) == _ASSET

    def test_uppercase_canonical_is_accepted_and_normalized(self) -> None:
        parsed = public_service.parse_public_uuid(str(_ASSET).upper())
        assert parsed == _ASSET
        # Normalized: the value used downstream is the canonical lowercase
        # form, so an uppercase URL addresses exactly the same object.
        assert str(parsed) == str(_ASSET)

    def test_mixed_case_canonical_is_accepted(self) -> None:
        raw = str(_ASSET)[:8].upper() + str(_ASSET)[8:]
        assert public_service.parse_public_uuid(raw) == _ASSET

    def test_non_contract_spellings_are_rejected(self) -> None:
        # Accepting these would mint alias URLs for one resource.
        for raw in (
            "{11111111-2222-3333-4444-555555555555}",
            "111111112222333344445555 55555555".replace(" ", ""),  # hyphenless
            "urn:uuid:11111111-2222-3333-4444-555555555555",
            "11111111-2222-3333-4444-555555555555 ",
            " 11111111-2222-3333-4444-555555555555",
        ):
            assert public_service.parse_public_uuid(raw) is None, raw

    def test_malformed_values_are_rejected(self) -> None:
        for raw in ("", "not-a-uuid", "1234", "../../etc/passwd", "11111111-2222-3333-4444"):
            assert public_service.parse_public_uuid(raw) is None, raw


class TestEtagDerivation:
    def test_etag_is_a_quoted_full_sha256_digest(self) -> None:
        etag = _etag()
        assert etag.startswith('"') and etag.endswith('"')
        assert len(etag) == 66  # 64 hex characters plus both quotes
        assert all(character in "0123456789abcdef" for character in etag[1:-1])

    def test_etag_is_stable_for_identical_input(self) -> None:
        assert _etag() == _etag()

    def test_etag_differs_per_variant_and_per_asset(self) -> None:
        assert _etag("canonical") != _etag("w320")
        other = public_service._derive_etag(uuid.uuid4(), "canonical", _CHECKSUM)
        assert other != _etag()

    def test_etag_differs_when_the_representation_checksum_differs(self) -> None:
        assert _etag(checksum="a" * 64) != _etag(checksum="b" * 64)

    def test_stored_checksum_is_never_exposed_in_the_etag(self) -> None:
        assert _CHECKSUM not in _etag()

    def test_etag_input_is_versioned(self) -> None:
        # The digest must cover a version marker, so the validator can be
        # invalidated without touching stored bytes.
        expected = hashlib.sha256(f"rem1|{_ASSET}|canonical|{_CHECKSUM}".encode()).hexdigest()
        assert _etag() == f'"{expected}"'


class TestIfNoneMatch:
    def test_absent_or_empty_header_never_matches(self) -> None:
        assert public_service.if_none_match_matches(None, _etag()) is False
        assert public_service.if_none_match_matches("", _etag()) is False

    def test_exact_validator_matches(self) -> None:
        assert public_service.if_none_match_matches(_etag(), _etag()) is True

    def test_wildcard_matches(self) -> None:
        assert public_service.if_none_match_matches("*", _etag()) is True

    def test_comma_separated_list_matches_any_member(self) -> None:
        header = f'"{"0" * 64}", {_etag()}, "{"f" * 64}"'
        assert public_service.if_none_match_matches(header, _etag()) is True

    def test_weak_validator_matches_for_get_and_head(self) -> None:
        assert public_service.if_none_match_matches(f"W/{_etag()}", _etag()) is True
        assert public_service.if_none_match_matches(f"w/{_etag()}", _etag()) is True

    def test_non_matching_and_unusable_values_fall_through(self) -> None:
        for header in ('"nope"', "garbage", "W/", ",,,", _etag().strip('"')):
            assert public_service.if_none_match_matches(header, _etag()) is False, header


class _RecordingStream:
    """A minimal binary stream that records how often it was closed."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0
        self.close_count = 0

    def read(self, size: int) -> bytes:
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.close_count += 1


class TestStreamCleanup:
    def test_full_consumption_closes_the_handle_once(self) -> None:
        stream = _RecordingStream(b"payload")
        assert b"".join(_stream_and_close(stream)) == b"payload"  # type: ignore[arg-type]
        assert stream.close_count == 1

    def test_client_disconnect_closes_the_handle(self) -> None:
        # Abandoning the generator mid-stream is what a disconnect looks
        # like to the response: the generator is closed with GeneratorExit.
        stream = _RecordingStream(b"x" * (128 * 1024))
        generator = cast(Generator[bytes], _stream_and_close(stream))  # type: ignore[arg-type]
        next(generator)
        generator.close()
        assert stream.close_count == 1

    def test_cleanup_emits_no_log_events(self) -> None:
        # Ordinary completion and disconnect are not storage faults and
        # must never look like one in the operational log.
        stream = _RecordingStream(b"payload")
        with structlog.testing.capture_logs() as logs:
            list(_stream_and_close(stream))  # type: ignore[arg-type]
            generator = cast(
                Generator[bytes],
                _stream_and_close(_RecordingStream(b"y" * 4096)),  # type: ignore[arg-type]
            )
            next(generator)
            generator.close()
        assert logs == []


class TestObjectAnomalyWarnings:
    def test_warning_carries_only_the_approved_fields(self) -> None:
        business_id = uuid.uuid4()
        with structlog.testing.capture_logs() as logs:
            public_service.warn_object_anomaly(
                "media_object_missing",
                business_id=business_id,
                asset_id=_ASSET,
                variant="w320",
            )
        (entry,) = logs
        assert entry["event"] == "media_object_missing"
        assert entry["log_level"] == "warning"
        assert entry["business_id"] == str(business_id)
        assert entry["asset_id"] == str(_ASSET)
        assert entry["variant"] == "w320"
        # No host, key, path, checksum, filename, or exception text.
        assert set(entry) == {"event", "log_level", "business_id", "asset_id", "variant"}


class TestRepresentationCarriesNoInternals:
    def test_representation_exposes_no_key_or_checksum(self) -> None:
        representation = PublicRepresentation(
            asset_id=_ASSET, variant="canonical", byte_size=10, etag=_etag()
        )
        fields: dict[str, Any] = representation.__dict__
        assert set(fields) == {"asset_id", "variant", "byte_size", "etag"}
        assert _CHECKSUM not in repr(representation)
