"""Public media delivery: authorization, validators, headers (M3D, ADR-017).

Extends the permanent isolation matrix (docs/04) to public image delivery.
The central rule under test is that ``status = 'active'`` is **necessary
but not sufficient**: promotion is one-way, so an asset that is detached,
hidden, or reachable only through an invisible category must stop being
publicly retrievable even for someone who kept its URL.

Every ineligible condition — unknown, foreign, pending, detached,
hidden-only, hidden-category-only, malformed id, unknown variant — must be
the *same* neutral 404, and none of them may write an operational warning
(logging expected public misses would be an unauthenticated
log-amplification vector).

Assets are seeded directly (row plus object) rather than uploaded: the
upload pipeline is M3C's subject, and these tests need many eligibility
combinations.
"""

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.domains.media.storage import MediaStorage, ObjectNotFoundError, object_key
from tests.security.conftest import CreateBusiness
from tests.security.test_public_menu import _seed_category, _seed_group, _seed_item

_CANONICAL = "canonical"
_PAYLOAD = b"RIFF\x00\x00\x00\x00WEBPVP8 fake-canonical-bytes"
_VARIANT_PAYLOAD = b"RIFF\x00\x00\x00\x00WEBPVP8 fake-w320-bytes"


def _url(asset_id: uuid.UUID | str, variant: str = _CANONICAL) -> str:
    return f"/api/v1/public/media/{asset_id}/{variant}"


def _host(host: str = "shalik.localhost") -> dict[str, str]:
    return {"host": host}


@pytest.fixture
def media_root(app: FastAPI) -> Path:
    """The per-test media root the app under test was composed with."""
    return Path(app.state.media_storage.root)


def _write_object(
    root: Path, business_id: uuid.UUID, asset_id: uuid.UUID, variant: str, data: bytes
) -> None:
    path = root / object_key(business_id, asset_id, variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _seed_asset(
    engine: Engine,
    root: Path,
    business_id: uuid.UUID,
    *,
    status: str = "active",
    with_variant: bool = True,
    canonical_bytes: bytes = _PAYLOAD,
    variant_bytes: bytes = _VARIANT_PAYLOAD,
    write_objects: bool = True,
) -> uuid.UUID:
    """Seed one asset row (plus a w320 variant) and its stored objects."""
    asset_id = uuid.uuid4()
    expiry = "now() + interval '48 hours'" if status == "pending" else "NULL"
    with engine.begin() as connection:
        connection.execute(
            text(
                # S608: expiry is one of two test-internal literals.
                "INSERT INTO media_assets (id, business_id, kind, status,"  # noqa: S608
                " pending_expires_at, original_filename, declared_content_type,"
                " source_format, width, height, byte_size, checksum_sha256)"
                f" VALUES (:id, :bid, 'image', :status, {expiry}, 'dish.jpg',"
                " 'image/jpeg', 'jpeg', 1200, 800, :bytes, :sha)"
            ),
            {
                "id": asset_id,
                "bid": business_id,
                "status": status,
                "bytes": len(canonical_bytes),
                "sha": hashlib.sha256(canonical_bytes).hexdigest(),
            },
        )
        if with_variant:
            connection.execute(
                text(
                    "INSERT INTO media_asset_variants (id, business_id, asset_id,"
                    " variant, width, height, byte_size, checksum_sha256) VALUES"
                    " (:id, :bid, :aid, 'w320', 320, 213, :bytes, :sha)"
                ),
                {
                    "id": uuid.uuid4(),
                    "bid": business_id,
                    "aid": asset_id,
                    "bytes": len(variant_bytes),
                    "sha": hashlib.sha256(variant_bytes).hexdigest(),
                },
            )
    if write_objects:
        _write_object(root, business_id, asset_id, _CANONICAL, canonical_bytes)
        if with_variant:
            _write_object(root, business_id, asset_id, "w320", variant_bytes)
    return asset_id


def _attach(
    engine: Engine, item_id: uuid.UUID, asset_id: uuid.UUID, alt: str | None = None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE menu_items SET image_media_id = :aid, image_alt_text = :alt WHERE id = :iid"
            ),
            {"aid": asset_id, "alt": alt, "iid": item_id},
        )


def _publishable(
    engine: Engine,
    root: Path,
    create_business: CreateBusiness,
    *,
    slug: str = "shalik",
    item_hidden: bool = False,
    category_visible: bool = True,
    item_available: bool = True,
    attach: bool = True,
    asset_status: str = "active",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """An active Business with one asset, optionally attached to one item."""
    business_id = create_business(slug=slug, name="Shalik", status="active")
    category_id = _seed_category(engine, business_id, is_visible=category_visible)
    item_id = _seed_item(
        engine, business_id, category_id, is_hidden=item_hidden, is_available=item_available
    )
    asset_id = _seed_asset(engine, root, business_id, status=asset_status)
    if attach:
        _attach(engine, item_id, asset_id)
    return business_id, item_id, asset_id


class _SpyStorage:
    """Delegating storage wrapper that records stat/open calls."""

    def __init__(self, inner: MediaStorage) -> None:
        self._inner = inner
        self.stat_calls = 0
        self.open_calls = 0
        self.fail_open = False

    def put(self, *, key: str, content: BinaryIO, content_type: str) -> None:
        self._inner.put(key=key, content=content, content_type=content_type)

    def open(self, *, key: str) -> BinaryIO:
        self.open_calls += 1
        if self.fail_open:
            raise ObjectNotFoundError(key)
        return self._inner.open(key=key)

    def delete(self, *, key: str) -> None:
        self._inner.delete(key=key)

    def stat(self, *, key: str) -> Any:
        self.stat_calls += 1
        return self._inner.stat(key=key)


@pytest.fixture
def spy_storage(app: FastAPI) -> _SpyStorage:
    spy = _SpyStorage(app.state.media_storage)
    app.state.media_storage = spy
    return spy


def _warnings(logs: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Captured warning-level events only (request logging is INFO)."""
    return [entry for entry in logs if entry.get("log_level") == "warning"]


def _assert_neutral_404(response: Any) -> None:
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Not found."
    assert body["error"]["details"] is None
    assert response.headers["cache-control"] == "no-store"


class TestSuccessfulDelivery:
    def test_canonical_delivery_carries_every_approved_header(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        response = client.get(_url(asset_id), headers=_host())
        assert response.status_code == 200
        assert response.content == _PAYLOAD
        assert response.headers["content-type"] == "image/webp"
        assert response.headers["content-disposition"] == "inline"
        assert response.headers["content-length"] == str(len(_PAYLOAD))
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "public, max-age=3600, immutable"
        etag = response.headers["etag"]
        assert etag.startswith('"') and etag.endswith('"')
        assert len(etag) == 66

    def test_derived_variant_is_delivered_with_its_own_validator(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        canonical = client.get(_url(asset_id), headers=_host())
        variant = client.get(_url(asset_id, "w320"), headers=_host())
        assert variant.status_code == 200
        assert variant.content == _VARIANT_PAYLOAD
        assert variant.headers["content-length"] == str(len(_VARIANT_PAYLOAD))
        # Each representation carries its own checksum-derived validator.
        assert variant.headers["etag"] != canonical.headers["etag"]

    def test_uppercase_asset_id_resolves_identically(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        lower = client.get(_url(asset_id), headers=_host())
        upper = client.get(_url(str(asset_id).upper()), headers=_host())
        assert upper.status_code == 200
        assert upper.content == lower.content
        assert upper.headers["etag"] == lower.headers["etag"]

    def test_no_storage_key_path_or_checksum_appears_in_the_response(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        response = client.get(_url(asset_id), headers=_host())
        headers = " ".join(f"{name}: {value}" for name, value in response.headers.items())
        assert object_key(business_id, asset_id, _CANONICAL) not in headers
        assert str(media_root) not in headers
        assert hashlib.sha256(_PAYLOAD).hexdigest() not in headers
        assert "dish.jpg" not in headers


class TestPublicAttachmentAuthorization:
    """Active status is necessary but never sufficient."""

    def test_detached_active_asset_is_not_deliverable(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business, attach=False)
        _assert_neutral_404(client.get(_url(asset_id), headers=_host()))

    def test_asset_attached_only_to_a_hidden_item_is_not_deliverable(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(
            migrated_engine, media_root, create_business, item_hidden=True
        )
        _assert_neutral_404(client.get(_url(asset_id), headers=_host()))

    def test_asset_attached_only_through_a_hidden_category_is_not_deliverable(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(
            migrated_engine, media_root, create_business, category_visible=False
        )
        _assert_neutral_404(client.get(_url(asset_id), headers=_host()))

    def test_sold_out_item_still_authorizes_its_image(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(
            migrated_engine, media_root, create_business, item_available=False
        )
        assert client.get(_url(asset_id), headers=_host()).status_code == 200

    def test_non_orderable_item_still_authorizes_its_image(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id, item_id, asset_id = _publishable(migrated_engine, media_root, create_business)
        # A required group with no available option: the item is listed but
        # not orderable, which is an ordering state, not a visibility one.
        _seed_group(
            migrated_engine,
            business_id,
            item_id,
            min_select=1,
            max_select=1,
            options=(("Sold Out", 0, False),),
        )
        assert client.get(_url(asset_id), headers=_host()).status_code == 200

    def test_one_public_attachment_is_enough(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id, visible_item, asset_id = _publishable(
            migrated_engine, media_root, create_business
        )
        category_id = _seed_category(migrated_engine, business_id, name="Hidden", position=1)
        hidden_item = _seed_item(
            migrated_engine, business_id, category_id, name="Hidden Dish", is_hidden=True
        )
        _attach(migrated_engine, hidden_item, asset_id)
        assert visible_item
        assert client.get(_url(asset_id), headers=_host()).status_code == 200

    def test_detaching_stops_delivery_for_a_previously_valid_url(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        # The reason active-status alone is insufficient: promotion is
        # one-way, so a retained URL must stop working when the image is
        # taken off the menu.
        _, item_id, asset_id = _publishable(migrated_engine, media_root, create_business)
        assert client.get(_url(asset_id), headers=_host()).status_code == 200
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE menu_items SET image_media_id = NULL, image_alt_text = NULL"
                    " WHERE id = :iid"
                ),
                {"iid": item_id},
            )
        _assert_neutral_404(client.get(_url(asset_id), headers=_host()))

    def test_pending_asset_is_never_publicly_deliverable(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(
            migrated_engine, media_root, create_business, asset_status="pending"
        )
        _assert_neutral_404(client.get(_url(asset_id), headers=_host()))


class TestResolutionAndIsolation:
    def test_unknown_asset_id_is_neutral_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _publishable(migrated_engine, media_root, create_business)
        _assert_neutral_404(client.get(_url(uuid.uuid4()), headers=_host()))

    def test_cross_tenant_asset_is_neutral_404_without_touching_storage(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
        spy_storage: _SpyStorage,
    ) -> None:
        _publishable(migrated_engine, media_root, create_business, slug="alpha")
        _, _, other_asset = _publishable(migrated_engine, media_root, create_business, slug="bravo")
        # Bravo's asset requested under Alpha's host.
        _assert_neutral_404(client.get(_url(other_asset), headers=_host("alpha.localhost")))
        assert spy_storage.stat_calls == 0
        assert spy_storage.open_calls == 0

    def test_unknown_host_and_inactive_business_are_neutral_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        _assert_neutral_404(client.get(_url(asset_id), headers=_host("nope.localhost")))
        with migrated_engine.begin() as connection:
            connection.execute(text("UPDATE businesses SET status = 'suspended'"))
        _assert_neutral_404(client.get(_url(asset_id), headers=_host()))

    def test_malformed_asset_id_is_the_neutral_404_not_a_422(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _publishable(migrated_engine, media_root, create_business)
        for raw in (
            "not-a-uuid",
            "1234",
            "%7B11111111-2222-3333-4444-555555555555%7D",
            "111111112222333344445555555555555",
        ):
            response = client.get(_url(raw), headers=_host())
            _assert_neutral_404(response)
            assert response.json()["error"]["field_errors"] == []

    def test_unknown_variant_is_neutral_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        for variant in ("w9999", "original", "thumbnail"):
            _assert_neutral_404(client.get(_url(asset_id, variant), headers=_host()))

    def test_missing_variant_row_is_neutral_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id = create_business(slug="shalik", status="active")
        category_id = _seed_category(migrated_engine, business_id)
        item_id = _seed_item(migrated_engine, business_id, category_id)
        asset_id = _seed_asset(migrated_engine, media_root, business_id, with_variant=False)
        _attach(migrated_engine, item_id, asset_id)
        assert client.get(_url(asset_id), headers=_host()).status_code == 200
        _assert_neutral_404(client.get(_url(asset_id, "w320"), headers=_host()))

    def test_no_authentication_is_required_and_unsafe_methods_are_rejected(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        assert client.get(_url(asset_id), headers=_host()).status_code == 200
        for request in (client.post, client.put, client.patch, client.delete):
            response = request(_url(asset_id), headers=_host())
            assert response.status_code == 405, request.__name__
            assert response.headers["cache-control"] == "no-store"


class TestConditionalRequests:
    def _etag(self, client: TestClient, asset_id: uuid.UUID, variant: str = _CANONICAL) -> str:
        return str(client.get(_url(asset_id, variant), headers=_host()).headers["etag"])

    def test_matching_validator_returns_304_without_a_body(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        etag = self._etag(client, asset_id)

        response = client.get(_url(asset_id), headers={**_host(), "If-None-Match": etag})
        assert response.status_code == 304
        assert response.content == b""
        assert "content-length" not in response.headers
        assert response.headers["etag"] == etag
        assert response.headers["cache-control"] == "public, max-age=3600, immutable"

    def test_matching_validator_stats_but_never_opens(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
        spy_storage: _SpyStorage,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        etag = self._etag(client, asset_id)
        opens_after_priming = spy_storage.open_calls

        response = client.get(_url(asset_id), headers={**_host(), "If-None-Match": etag})
        assert response.status_code == 304
        # The physical object is still verified before a 304 is issued...
        assert spy_storage.stat_calls >= 2
        # ...but its contents are never read.
        assert spy_storage.open_calls == opens_after_priming

    def test_wildcard_comma_list_and_weak_validators_match(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        etag = self._etag(client, asset_id)
        for header in ("*", f'"{"0" * 64}", {etag}', f"W/{etag}"):
            response = client.get(_url(asset_id), headers={**_host(), "If-None-Match": header})
            assert response.status_code == 304, header

    def test_non_matching_or_unusable_validator_returns_the_full_body(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        for header in (f'"{"0" * 64}"', "garbage", "W/"):
            response = client.get(_url(asset_id), headers={**_host(), "If-None-Match": header})
            assert response.status_code == 200, header
            assert response.content == _PAYLOAD

    def test_a_variants_validator_does_not_match_the_canonical(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        variant_etag = self._etag(client, asset_id, "w320")
        response = client.get(_url(asset_id), headers={**_host(), "If-None-Match": variant_etag})
        assert response.status_code == 200

    def test_matching_validator_with_a_missing_object_is_404_not_304(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        etag = self._etag(client, asset_id)
        (media_root / object_key(business_id, asset_id, _CANONICAL)).unlink()

        response = client.get(_url(asset_id), headers={**_host(), "If-None-Match": etag})
        _assert_neutral_404(response)

    def test_matching_validator_with_a_size_mismatch_is_404_not_304(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        etag = self._etag(client, asset_id)
        (media_root / object_key(business_id, asset_id, _CANONICAL)).write_bytes(b"short")

        response = client.get(_url(asset_id), headers={**_host(), "If-None-Match": etag})
        _assert_neutral_404(response)


class TestObjectAnomalies:
    def test_missing_object_is_404_with_one_bounded_warning(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        (media_root / object_key(business_id, asset_id, _CANONICAL)).unlink()

        with structlog.testing.capture_logs() as logs:
            response = client.get(_url(asset_id), headers=_host())
        _assert_neutral_404(response)
        warnings = _warnings(logs)
        assert [entry["event"] for entry in warnings] == ["media_object_missing"]
        # Exactly the approved payload: a reason code plus the three
        # identifiers. Static context (service, environment, request id) is
        # added by the shared processors, not by this call site.
        assert set(warnings[0]) == {"event", "log_level", "business_id", "asset_id", "variant"}
        assert warnings[0]["asset_id"] == str(asset_id)

    def test_size_mismatch_is_404_with_a_size_warning(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        business_id, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        (media_root / object_key(business_id, asset_id, _CANONICAL)).write_bytes(b"tiny")

        with structlog.testing.capture_logs() as logs:
            response = client.get(_url(asset_id), headers=_host())
        _assert_neutral_404(response)
        assert [entry["event"] for entry in _warnings(logs)] == ["media_object_size_mismatch"]

    def test_open_failure_after_a_successful_stat_is_a_clean_404(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
        spy_storage: _SpyStorage,
    ) -> None:
        # The stat/open race: the object vanishes between verification and
        # read. No response header may have been committed, so this is a
        # neutral 404 and never a 200 that stops short of Content-Length.
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        spy_storage.fail_open = True

        with structlog.testing.capture_logs() as logs:
            response = client.get(_url(asset_id), headers=_host())
        _assert_neutral_404(response)
        assert "content-length" not in response.headers or response.headers[
            "content-length"
        ] != str(len(_PAYLOAD))
        assert [entry["event"] for entry in _warnings(logs)] == ["media_object_unreadable"]
        assert spy_storage.open_calls == 1

    def test_expected_public_misses_never_warn(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        # Logging ordinary misses would hand an unauthenticated caller a
        # log-amplification vector.
        business_id, item_id, asset_id = _publishable(migrated_engine, media_root, create_business)
        detached = _seed_asset(migrated_engine, media_root, business_id)
        with structlog.testing.capture_logs() as logs:
            client.get(_url(uuid.uuid4()), headers=_host())  # unknown
            client.get(_url(detached), headers=_host())  # detached
            client.get(_url("not-a-uuid"), headers=_host())  # malformed
            client.get(_url(asset_id, "w9999"), headers=_host())  # unknown variant
            client.get(_url(asset_id), headers=_host("nope.localhost"))  # unknown host
        assert item_id
        assert _warnings(logs) == []

    def test_successful_delivery_emits_no_warning(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        with structlog.testing.capture_logs() as logs:
            assert client.get(_url(asset_id), headers=_host()).status_code == 200
        assert _warnings(logs) == []


class TestHeadAndRangePolicy:
    def test_head_returns_representation_headers_without_opening_the_object(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
        spy_storage: _SpyStorage,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        head = client.head(_url(asset_id), headers=_host())
        assert head.status_code == 200
        assert head.content == b""
        assert head.headers["content-type"] == "image/webp"
        assert head.headers["content-length"] == str(len(_PAYLOAD))
        assert head.headers["content-disposition"] == "inline"
        assert head.headers["x-content-type-options"] == "nosniff"
        assert head.headers["cache-control"] == "public, max-age=3600, immutable"
        assert head.headers["etag"]
        assert spy_storage.stat_calls == 1
        assert spy_storage.open_calls == 0

    def test_head_matches_the_get_representation_headers(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)
        head = client.head(_url(asset_id), headers=_host())
        get = client.get(_url(asset_id), headers=_host())
        for header in (
            "content-type",
            "content-length",
            "content-disposition",
            "x-content-type-options",
            "cache-control",
            "etag",
        ):
            assert head.headers[header] == get.headers[header], header

    def test_head_errors_stay_neutral_and_uncacheable(
        self, client: TestClient, create_business: CreateBusiness
    ) -> None:
        create_business(slug="shalik", status="active")
        response = client.head(_url(uuid.uuid4()), headers=_host())
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"

    def test_range_requests_are_ignored_and_return_the_full_representation(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        response = client.get(_url(asset_id), headers={**_host(), "Range": "bytes=0-3"})
        assert response.status_code == 200
        assert response.content == _PAYLOAD
        assert "content-range" not in response.headers
        assert "accept-ranges" not in response.headers


class TestNoAuditForPublicReads:
    def test_get_head_and_304_write_no_audit_event(
        self,
        client: TestClient,
        create_business: CreateBusiness,
        migrated_engine: Engine,
        media_root: Path,
    ) -> None:
        _, _, asset_id = _publishable(migrated_engine, media_root, create_business)

        def _count() -> int:
            with migrated_engine.begin() as connection:
                return int(
                    connection.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
                )

        before = _count()
        etag = client.get(_url(asset_id), headers=_host()).headers["etag"]
        client.head(_url(asset_id), headers=_host())
        client.get(_url(asset_id), headers={**_host(), "If-None-Match": etag})
        client.get(_url(uuid.uuid4()), headers=_host())
        client.get("/api/v1/public/menu", headers=_host())
        assert _count() == before
