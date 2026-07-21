"""Backup verification (M3C, ADR-017, final correction 3).

``verify_backup`` recomputes every stored object's SHA-256 and byte size
against the database, flags every storage-only object regardless of age,
gives malformed keys an explicit non-success disposition, and never
mutates. Findings carry business/asset/variant only — never a key, path,
or checksum value.
"""

import hashlib
import io
import uuid
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.domains.media import sweep
from app.domains.media.storage import LocalFilesystemStorage, object_key


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


def _business(engine: Engine) -> uuid.UUID:
    business_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO businesses (id, name, slug, status) VALUES"
                " (:id, 'Verify Biz', :slug, 'active')"
            ),
            {"id": business_id, "slug": f"verify-{business_id.hex[:8]}"},
        )
    return business_id


def _put(
    storage: LocalFilesystemStorage,
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    variant: str,
    data: bytes,
) -> tuple[int, str]:
    storage.put(
        key=object_key(business_id, asset_id, variant),
        content=io.BytesIO(data),
        content_type="image/webp",
    )
    return len(data), hashlib.sha256(data).hexdigest()


def _seed_consistent(
    engine: Engine, storage: LocalFilesystemStorage, business_id: uuid.UUID
) -> uuid.UUID:
    """Seed an asset + one variant whose rows match the stored objects."""
    asset_id = uuid.uuid4()
    c_size, c_sha = _put(storage, business_id, asset_id, "canonical", b"canonical-bytes-1234")
    v_size, v_sha = _put(storage, business_id, asset_id, "w320", b"variant-bytes-320")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO media_assets (id, business_id, kind, status,"
                " pending_expires_at, original_filename, declared_content_type,"
                " source_format, width, height, byte_size, checksum_sha256) VALUES"
                " (:id, :bid, 'image', 'active', NULL, 'x.jpg', 'image/jpeg', 'jpeg',"
                " 800, 600, :size, :sha)"
            ),
            {"id": asset_id, "bid": business_id, "size": c_size, "sha": c_sha},
        )
        connection.execute(
            text(
                "INSERT INTO media_asset_variants (id, business_id, asset_id, variant,"
                " width, height, byte_size, checksum_sha256) VALUES"
                " (:id, :bid, :aid, 'w320', 320, 240, :size, :sha)"
            ),
            {"id": uuid.uuid4(), "bid": business_id, "aid": asset_id, "size": v_size, "sha": v_sha},
        )
    return asset_id


def _kinds(report: sweep.VerifyReport) -> set[str]:
    return {finding.kind for finding in report.findings}


class TestVerifyBackup:
    def test_fully_consistent_pair_is_ok(self, migrated_engine: Engine, tmp_path: Path) -> None:
        storage = LocalFilesystemStorage(tmp_path / "verify")
        business_id = _business(migrated_engine)
        _seed_consistent(migrated_engine, storage, business_id)
        report = sweep.verify_backup(_factory(migrated_engine), storage)
        assert report.ok
        assert report.findings == []
        assert report.malformed_keys == 0

    def test_canonical_tampering_is_a_checksum_mismatch(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        storage = LocalFilesystemStorage(tmp_path / "verify")
        business_id = _business(migrated_engine)
        asset_id = _seed_consistent(migrated_engine, storage, business_id)
        # Overwrite the canonical object with same-length but different bytes.
        _put(storage, business_id, asset_id, "canonical", b"tampered-bytes-XXXXX")
        report = sweep.verify_backup(_factory(migrated_engine), storage)
        assert not report.ok
        finding = next(f for f in report.findings if f.variant == "canonical")
        assert finding.kind == "checksum_mismatch"

    def test_variant_tampering_is_a_checksum_mismatch(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        storage = LocalFilesystemStorage(tmp_path / "verify")
        business_id = _business(migrated_engine)
        asset_id = _seed_consistent(migrated_engine, storage, business_id)
        _put(storage, business_id, asset_id, "w320", b"tampered-variant!")
        report = sweep.verify_backup(_factory(migrated_engine), storage)
        assert {f.variant for f in report.findings} == {"w320"}
        assert _kinds(report) == {"checksum_mismatch"}

    def test_size_mismatch_is_reported(self, migrated_engine: Engine, tmp_path: Path) -> None:
        storage = LocalFilesystemStorage(tmp_path / "verify")
        business_id = _business(migrated_engine)
        asset_id = _seed_consistent(migrated_engine, storage, business_id)
        # Different length than the recorded byte_size.
        _put(storage, business_id, asset_id, "canonical", b"short")
        report = sweep.verify_backup(_factory(migrated_engine), storage)
        finding = next(f for f in report.findings if f.variant == "canonical")
        assert finding.kind == "size_mismatch"

    def test_missing_object_is_reported(self, migrated_engine: Engine, tmp_path: Path) -> None:
        storage = LocalFilesystemStorage(tmp_path / "verify")
        business_id = _business(migrated_engine)
        asset_id = _seed_consistent(migrated_engine, storage, business_id)
        storage.delete(key=object_key(business_id, asset_id, "w320"))
        report = sweep.verify_backup(_factory(migrated_engine), storage)
        assert not report.ok
        finding = next(f for f in report.findings if f.variant == "w320")
        assert finding.kind == "missing"

    def test_young_storage_only_object_is_flagged_as_orphan(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        # Verify (unlike the sweep) flags storage-only objects at ANY age:
        # a quiesced backup set must contain none.
        storage = LocalFilesystemStorage(tmp_path / "verify")
        business_id = _business(migrated_engine)
        orphan_asset = uuid.uuid4()
        _put(storage, business_id, orphan_asset, "canonical", b"fresh-orphan-bytes")
        report = sweep.verify_backup(_factory(migrated_engine), storage)
        assert not report.ok
        finding = next(f for f in report.findings if f.asset_id == orphan_asset)
        assert finding.kind == "orphan"

    def test_malformed_entry_is_non_success(self, migrated_engine: Engine, tmp_path: Path) -> None:
        storage = LocalFilesystemStorage(tmp_path / "verify")
        storage.root.mkdir(parents=True, exist_ok=True)
        (storage.root / "operator-note.txt").write_bytes(b"not a media object")
        report = sweep.verify_backup(_factory(migrated_engine), storage)
        assert report.malformed_keys == 1
        assert not report.ok

    def test_verify_never_mutates(self, migrated_engine: Engine, tmp_path: Path) -> None:
        storage = LocalFilesystemStorage(tmp_path / "verify")
        business_id = _business(migrated_engine)
        asset_id = _seed_consistent(migrated_engine, storage, business_id)
        sweep.verify_backup(_factory(migrated_engine), storage)
        # Objects and rows are untouched.
        assert storage.stat(key=object_key(business_id, asset_id, "canonical")) is not None
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM media_assets WHERE id = :id"), {"id": asset_id}
                ).scalar_one()
                == 1
            )
