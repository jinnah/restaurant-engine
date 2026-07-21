"""Storage key derivation and the local filesystem adapter (M3C).

Pure filesystem behavior against pytest temp directories — no database,
no application settings, and never the development media root.
"""

import io
import time
import uuid
from pathlib import Path

import pytest

from app.domains.media.storage import (
    TMP_DIR_NAME,
    LocalFilesystemStorage,
    ObjectNotFoundError,
    object_key,
    parse_key,
)

BIZ = uuid.uuid4()
ASSET = uuid.uuid4()


def _adapter(tmp_path: Path) -> LocalFilesystemStorage:
    return LocalFilesystemStorage(tmp_path / "media-root")


class TestKeys:
    def test_object_key_shape_is_tenant_prefixed_and_derived(self) -> None:
        key = object_key(BIZ, ASSET, "canonical")
        assert key == f"{BIZ}/{ASSET}/canonical.webp"
        assert object_key(BIZ, ASSET, "w320").endswith("/w320.webp")

    def test_unknown_variant_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="unknown logical variant"):
            object_key(BIZ, ASSET, "w2000")

    def test_parse_round_trips_valid_keys(self) -> None:
        parsed = parse_key(object_key(BIZ, ASSET, "w640"))
        assert parsed is not None
        assert parsed.business_id == BIZ
        assert parsed.asset_id == ASSET
        assert parsed.variant == "w640"

    @pytest.mark.parametrize(
        "malformed",
        [
            "not-a-key",
            "../../etc/passwd",
            f"{uuid.uuid4()}/{uuid.uuid4()}/w2000.webp",  # unknown variant
            f"{uuid.uuid4()}/{uuid.uuid4()}/canonical.png",  # wrong suffix
            f"{uuid.uuid4()}/canonical.webp",  # missing asset segment
            f"{uuid.uuid4()}/{uuid.uuid4()}/{uuid.uuid4()}/canonical.webp",
            f"{uuid.uuid4()}/{uuid.uuid4()}/CANONICAL.webp",  # case matters
        ],
    )
    def test_parse_rejects_malformed_shapes(self, malformed: str) -> None:
        assert parse_key(malformed) is None


class TestLocalFilesystemStorage:
    def test_put_invokes_target_directory_fsync_after_replace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Durability (round-2 finding 2): put fsyncs the target directory
        # after os.replace. Proven cross-platform by observing the call
        # (the fsync itself is a POSIX no-op on Windows).
        from app.domains.media import storage as storage_module

        calls: list[Path] = []
        monkeypatch.setattr(storage_module, "_fsync_directory", calls.append)
        storage = _adapter(tmp_path)
        key = object_key(BIZ, ASSET, "canonical")
        storage.put(key=key, content=io.BytesIO(b"webp"), content_type="image/webp")
        target = storage._path(key)
        assert calls == [target.parent]

    def test_put_open_stat_delete_round_trip(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)
        key = object_key(BIZ, ASSET, "canonical")
        storage.put(key=key, content=io.BytesIO(b"webp-bytes"), content_type="image/webp")
        with storage.open(key=key) as handle:
            assert handle.read() == b"webp-bytes"
        stat = storage.stat(key=key)
        assert stat is not None
        assert stat.byte_size == len(b"webp-bytes")
        assert stat.key == key
        assert stat.last_modified.tzinfo is not None
        storage.delete(key=key)
        assert storage.stat(key=key) is None
        #

        # Empty asset/business directories are pruned best-effort.
        assert not (storage.root / str(BIZ)).exists()

    def test_open_missing_raises_object_not_found(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)
        with pytest.raises(ObjectNotFoundError):
            storage.open(key=object_key(BIZ, ASSET, "canonical"))

    def test_delete_is_idempotent(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)
        storage.delete(key=object_key(BIZ, ASSET, "canonical"))  # no error

    @pytest.mark.parametrize(
        "bad_key",
        ["../escape.webp", "..\\escape.webp", "plain.webp", "a/b/c/d/e.webp"],
    )
    def test_every_operation_rejects_malformed_keys(self, tmp_path: Path, bad_key: str) -> None:
        storage = _adapter(tmp_path)
        with pytest.raises(ValueError, match="invalid storage key"):
            storage.put(key=bad_key, content=io.BytesIO(b"x"), content_type="image/webp")
        with pytest.raises(ValueError, match="invalid storage key"):
            storage.open(key=bad_key)
        with pytest.raises(ValueError, match="invalid storage key"):
            storage.delete(key=bad_key)
        with pytest.raises(ValueError, match="invalid storage key"):
            storage.stat(key=bad_key)

    def test_iter_objects_reports_everything_except_tmp(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)
        key = object_key(BIZ, ASSET, "w320")
        storage.put(key=key, content=io.BytesIO(b"v"), content_type="image/webp")
        # A malformed foreign file must be VISIBLE (report-only for the
        # sweep), while .tmp scratch must not be.
        stray = storage.root / str(BIZ) / "stray.txt"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_bytes(b"?")
        (storage.root / TMP_DIR_NAME).mkdir(parents=True, exist_ok=True)
        (storage.root / TMP_DIR_NAME / "scratch").write_bytes(b"ignored")

        keys = {item.key for item in storage.iter_objects()}
        assert keys == {key, f"{BIZ}/stray.txt"}

    def test_iter_objects_prefix_filter(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)
        other_biz = uuid.uuid4()
        storage.put(
            key=object_key(BIZ, ASSET, "canonical"),
            content=io.BytesIO(b"a"),
            content_type="image/webp",
        )
        storage.put(
            key=object_key(other_biz, uuid.uuid4(), "canonical"),
            content=io.BytesIO(b"b"),
            content_type="image/webp",
        )
        keys = {item.key for item in storage.iter_objects(prefix=f"{BIZ}/")}
        assert keys == {object_key(BIZ, ASSET, "canonical")}

    def test_probe_writes_and_cleans_a_unique_marker(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)
        storage.probe()
        leftovers = list((storage.root / TMP_DIR_NAME).iterdir())
        assert leftovers == []

    def test_startup_check_requires_existing_root(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)  # root not created yet
        with pytest.raises(RuntimeError, match="MEDIA_STORAGE_ROOT"):
            storage.startup_check()
        storage.root.mkdir(parents=True)
        storage.startup_check()  # now passes

    def test_cleanup_stale_temps_uses_age_and_spares_fresh_files(self, tmp_path: Path) -> None:
        storage = _adapter(tmp_path)
        tmp_dir = storage.root / TMP_DIR_NAME
        tmp_dir.mkdir(parents=True)
        stale = tmp_dir / "stale"
        fresh = tmp_dir / "fresh"
        stale.write_bytes(b"old")
        fresh.write_bytes(b"new")
        old = time.time() - 25 * 3600
        import os

        os.utime(stale, (old, old))
        removed = storage.cleanup_stale_temps(older_than_hours=24)
        assert removed == 1
        assert not stale.exists()
        assert fresh.exists()
