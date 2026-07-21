"""Media sweep and expiration boundaries (M3C, ADR-017, final corrections J/K/N).

Covers the four sweep categories, lifecycle independence (closed
businesses are still swept), object-level orphan identity, malformed-key
report-only behavior, the missing-object report, and the expired-pending
attach boundary trio (before / exactly at / after expiry).
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.domains.media import sweep
from app.domains.media.storage import LocalFilesystemStorage, object_key

_SHA = "0" * 63 + "a"


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


def _make_business(engine: Engine, *, status: str = "active", slug: str | None = None) -> uuid.UUID:
    business_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO businesses (id, name, slug, status) VALUES"
                " (:id, :name, :slug, :status)"
            ),
            {
                "id": business_id,
                "name": "Sweep Biz",
                "slug": slug or f"sweep-{business_id.hex[:8]}",
                "status": status,
            },
        )
    return business_id


def _make_asset(
    engine: Engine,
    business_id: uuid.UUID,
    *,
    status: str = "pending",
    expires_in_hours: float | None = 48,
    variants: tuple[str, ...] = ("w320",),
) -> uuid.UUID:
    asset_id = uuid.uuid4()
    if status == "active":
        expiry = "NULL"
    else:
        expiry = f"now() + interval '{expires_in_hours} hours'"
    with engine.begin() as connection:
        connection.execute(
            text(
                # S608: expiry is a test-internal literal.
                "INSERT INTO media_assets (id, business_id, kind, status,"  # noqa: S608
                " pending_expires_at, original_filename, declared_content_type,"
                " source_format, width, height, byte_size, checksum_sha256)"
                f" VALUES (:id, :bid, 'image', :status, {expiry}, 'x.jpg',"
                " 'image/jpeg', 'jpeg', 800, 600, 5000, :sha)"
            ),
            {"id": asset_id, "bid": business_id, "status": status, "sha": _SHA},
        )
        for variant in variants:
            connection.execute(
                text(
                    "INSERT INTO media_asset_variants (id, business_id, asset_id,"
                    " variant, width, height, byte_size, checksum_sha256) VALUES"
                    " (:id, :bid, :aid, :variant, 320, 240, 1000, :sha)"
                ),
                {
                    "id": uuid.uuid4(),
                    "bid": business_id,
                    "aid": asset_id,
                    "variant": variant,
                    "sha": _SHA,
                },
            )
    return asset_id


def _write_objects(
    storage: LocalFilesystemStorage,
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    variants: tuple[str, ...] = ("canonical", "w320"),
) -> None:
    import io

    for variant in variants:
        storage.put(
            key=object_key(business_id, asset_id, variant),
            content=io.BytesIO(b"webp"),
            content_type="image/webp",
        )


def _storage(tmp_path: Path) -> LocalFilesystemStorage:
    return LocalFilesystemStorage(tmp_path / "sweep-media")


class TestExpiredPendingSweep:
    def test_dry_run_reports_without_deleting(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        business_id = _make_business(migrated_engine)
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=-1)
        storage = _storage(tmp_path)
        _write_objects(storage, business_id, asset_id)

        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=False)
        assert report.expired_pending_deleted == 1
        # Nothing was actually removed.
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM media_assets WHERE id = :id"), {"id": asset_id}
                ).scalar_one()
                == 1
            )
        assert storage.stat(key=object_key(business_id, asset_id, "canonical")) is not None

    def test_apply_deletes_row_objects_and_audits(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        business_id = _make_business(migrated_engine)
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=-1)
        storage = _storage(tmp_path)
        _write_objects(storage, business_id, asset_id)

        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        assert report.expired_pending_deleted == 1
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM media_assets WHERE id = :id"), {"id": asset_id}
                ).scalar_one()
                == 0
            )
            # NULL-actor system audit event.
            event = connection.execute(
                text(
                    "SELECT actor_user_id, details FROM audit_events"
                    " WHERE action = 'media.asset_expired' AND target_id = :aid"
                ),
                {"aid": str(asset_id)},
            ).one()
        assert event.actor_user_id is None
        assert event.details["trigger"] == "pending_ttl_sweep"
        assert storage.stat(key=object_key(business_id, asset_id, "canonical")) is None

    def test_unexpired_pending_is_not_swept(self, migrated_engine: Engine, tmp_path: Path) -> None:
        business_id = _make_business(migrated_engine)
        _make_asset(migrated_engine, business_id, expires_in_hours=48)
        report = sweep.run_sweep(_factory(migrated_engine), _storage(tmp_path), apply=True)
        assert report.expired_pending_deleted == 0

    def test_closed_business_expired_pending_is_still_swept(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        # Lifecycle independence (final correction 4): closed businesses are
        # NOT exempt from system TTL cleanup.
        business_id = _make_business(migrated_engine, status="closed")
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=-1)
        storage = _storage(tmp_path)
        _write_objects(storage, business_id, asset_id)
        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        assert report.expired_pending_deleted == 1
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM media_assets WHERE id = :id"), {"id": asset_id}
                ).scalar_one()
                == 0
            )

    def test_active_asset_is_never_swept(self, migrated_engine: Engine, tmp_path: Path) -> None:
        business_id = _make_business(migrated_engine)
        _make_asset(migrated_engine, business_id, status="active", variants=())
        report = sweep.run_sweep(_factory(migrated_engine), _storage(tmp_path), apply=True)
        assert report.expired_pending_deleted == 0


class TestOrphanSweep:
    def test_orphan_object_older_than_safety_age_is_deleted(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        import os

        business_id = _make_business(migrated_engine)
        storage = _storage(tmp_path)
        # An object with NO asset row = orphan.
        orphan_asset = uuid.uuid4()
        _write_objects(storage, business_id, orphan_asset, ("canonical",))
        # Age it beyond 24 h.
        path = storage._path(object_key(business_id, orphan_asset, "canonical"))
        old = (datetime.now(UTC) - timedelta(hours=25)).timestamp()
        os.utime(path, (old, old))

        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        assert report.orphans_deleted == 1
        assert storage.stat(key=object_key(business_id, orphan_asset, "canonical")) is None

    def test_young_orphan_is_spared(self, migrated_engine: Engine, tmp_path: Path) -> None:
        business_id = _make_business(migrated_engine)
        storage = _storage(tmp_path)
        orphan_asset = uuid.uuid4()
        _write_objects(storage, business_id, orphan_asset, ("canonical",))
        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        assert report.orphans_deleted == 0
        assert report.orphans_too_young == 1
        assert storage.stat(key=object_key(business_id, orphan_asset, "canonical")) is not None

    def test_variant_object_without_its_row_is_an_orphan(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        import os

        business_id = _make_business(migrated_engine)
        storage = _storage(tmp_path)
        # An asset row with ONLY a w320 variant row, but a w640 object exists
        # on disk with no matching row -> the w640 object is an orphan.
        asset_id = _make_asset(migrated_engine, business_id, status="active", variants=("w320",))
        # Fix the asset to active with no expiry already done.
        _write_objects(storage, business_id, asset_id, ("canonical", "w320", "w640"))
        stray = storage._path(object_key(business_id, asset_id, "w640"))
        old = (datetime.now(UTC) - timedelta(hours=25)).timestamp()
        os.utime(stray, (old, old))
        # Age the legitimate objects too, to prove they are NOT deleted.
        for keep in ("canonical", "w320"):
            os.utime(storage._path(object_key(business_id, asset_id, keep)), (old, old))

        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        assert report.orphans_deleted == 1  # only the w640 stray
        assert storage.stat(key=object_key(business_id, asset_id, "w640")) is None
        assert storage.stat(key=object_key(business_id, asset_id, "canonical")) is not None

    def test_malformed_key_is_report_only(self, migrated_engine: Engine, tmp_path: Path) -> None:
        import os

        storage = _storage(tmp_path)
        storage.root.mkdir(parents=True, exist_ok=True)
        stray = storage.root / "operator-notes.txt"
        stray.write_bytes(b"not a media object")
        old = (datetime.now(UTC) - timedelta(hours=48)).timestamp()
        os.utime(stray, (old, old))

        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        assert report.malformed_keys == 1
        assert report.orphans_deleted == 0
        assert stray.exists(), "a malformed/unknown key is never deleted"


class TestMissingObjectReport:
    def test_asset_row_missing_its_object_is_reported_not_deleted(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        business_id = _make_business(migrated_engine)
        storage = _storage(tmp_path)
        # Row exists (active, canonical + w320) but NO objects on disk.
        asset_id = _make_asset(migrated_engine, business_id, status="active", variants=("w320",))
        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        variants = {m.variant for m in report.missing_objects if m.asset_id == asset_id}
        assert variants == {"canonical", "w320"}
        # The row is NEVER auto-deleted.
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM media_assets WHERE id = :id"), {"id": asset_id}
                ).scalar_one()
                == 1
            )


class TestSweepSemantics:
    """Final correction 4: DB-clock selection, multi-batch, race re-read,
    per-object failure isolation, and dry-run stale-temp visibility."""

    def test_selection_uses_database_clock_not_the_application_clock(
        self, migrated_engine: Engine, tmp_path: Path, monkeypatch: object
    ) -> None:
        # An asset NOT expired on the database clock (+1h) must not be swept
        # even when the application clock is pushed 2h into the future.
        business_id = _make_business(migrated_engine)
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=1)

        real_datetime = datetime

        class _FutureClock(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
                return real_datetime.now(tz) + timedelta(hours=2)  # type: ignore[arg-type]

        import app.domains.media.sweep as sweep_module

        monkeypatch.setattr(sweep_module, "datetime", _FutureClock)  # type: ignore[attr-defined]
        report = sweep.run_sweep(_factory(migrated_engine), _storage(tmp_path), apply=True)
        assert report.expired_pending_deleted == 0
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM media_assets WHERE id = :id"), {"id": asset_id}
                ).scalar_one()
                == 1
            )

    def test_more_than_one_batch_is_processed(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        business_id = _make_business(migrated_engine)
        asset_ids = [
            _make_asset(migrated_engine, business_id, expires_in_hours=-1, variants=())
            for _ in range(5)
        ]
        # batch_size=2 forces at least three keyset passes.
        report = sweep.run_sweep(
            _factory(migrated_engine), _storage(tmp_path), apply=True, batch_size=2
        )
        assert report.expired_pending_deleted == 5
        with migrated_engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT count(*) FROM media_assets WHERE business_id = :bid"),
                {"bid": business_id},
            ).scalar_one()
        assert remaining == 0
        assert asset_ids  # (referenced for clarity)

    def test_candidate_promoted_before_the_lock_is_not_deleted(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        # Lock/re-read race (final correction K): a candidate that becomes
        # active between selection and the lock is skipped.
        from app.domains.media import repository
        from app.domains.media import sweep as sweep_module

        business_id = _make_business(migrated_engine)
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=-1)
        factory = _factory(migrated_engine)
        with factory() as db:
            candidates = repository.list_expired_pending_after(db, after_id=None, limit=10)
        assert (business_id, asset_id) in candidates
        # An attach wins the race: the row is now active before we process it.
        with migrated_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE media_assets SET status = 'active', pending_expires_at = NULL"
                    " WHERE id = :id"
                ),
                {"id": asset_id},
            )
        report = sweep.SweepReport(apply=True)
        sweep_module._sweep_business_expired(
            factory, _storage(tmp_path), report, business_id, [asset_id]
        )
        assert report.expired_pending_deleted == 0
        with migrated_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT status FROM media_assets WHERE id = :id"), {"id": asset_id}
                ).scalar_one()
                == "active"
            )

    def test_object_delete_failure_isolation_and_batch_continuation(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        business_id = _make_business(migrated_engine)
        for _ in range(2):
            _make_asset(migrated_engine, business_id, expires_in_hours=-1, variants=("w320",))
        base = _storage(tmp_path)

        class DeleteFailingStorage(LocalFilesystemStorage):
            def delete(self, *, key: str) -> None:
                raise OSError("object store down")

        storage = DeleteFailingStorage(base.root)
        report = sweep.run_sweep(_factory(migrated_engine), storage, apply=True)
        # Both rows are still deleted (committed); every object delete failed
        # but each was isolated and counted — the batch continued.
        assert report.expired_pending_deleted == 2
        assert report.expired_object_delete_failures == 4  # 2 assets x (canonical + w320)
        with migrated_engine.connect() as connection:
            remaining = connection.execute(
                text("SELECT count(*) FROM media_assets WHERE business_id = :bid"),
                {"bid": business_id},
            ).scalar_one()
        assert remaining == 0

    def test_dry_run_reports_stale_temps_without_deleting(
        self, migrated_engine: Engine, tmp_path: Path
    ) -> None:
        import os

        storage = _storage(tmp_path)
        storage.root.mkdir(parents=True, exist_ok=True)
        tmp_dir = storage.root / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        stale = tmp_dir / "encode-old.webp"
        stale.write_bytes(b"scratch")
        old = (datetime.now(UTC) - timedelta(hours=48)).timestamp()
        os.utime(stale, (old, old))

        factory = _factory(migrated_engine)
        dry = sweep.run_sweep(factory, storage, apply=False)
        assert dry.stale_temps_deleted == 1  # would-delete count
        assert stale.exists()  # nothing removed in dry run
        applied = sweep.run_sweep(factory, storage, apply=True)
        assert applied.stale_temps_deleted == 1
        assert not stale.exists()


class TestExpirationBoundary:
    """The attach decision on the database clock (final correction J)."""

    def _set_expiry(self, engine: Engine, asset_id: uuid.UUID, sql: str) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    # S608: sql is a test-internal literal.
                    f"UPDATE media_assets SET pending_expires_at = {sql}"  # noqa: S608
                    " WHERE id = :id"
                ),
                {"id": asset_id},
            )

    def _attachable(self, engine: Engine, business_id: uuid.UUID, asset_id: uuid.UUID) -> bool:
        from app.core.errors import InvalidStateError
        from app.domains.media.service import claim_for_attachment

        factory = _factory(engine)
        with factory() as db:
            try:
                claim_for_attachment(db, business_id, asset_id)
                db.rollback()
                return True
            except InvalidStateError:
                db.rollback()
                return False

    def test_future_expiry_is_attachable(self, migrated_engine: Engine) -> None:
        business_id = _make_business(migrated_engine)
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=1)
        assert self._attachable(migrated_engine, business_id, asset_id) is True

    def test_past_expiry_is_not_attachable(self, migrated_engine: Engine) -> None:
        business_id = _make_business(migrated_engine)
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=1)
        self._set_expiry(migrated_engine, asset_id, "now() - interval '1 second'")
        assert self._attachable(migrated_engine, business_id, asset_id) is False

    def test_exact_expiry_is_not_attachable(self, migrated_engine: Engine) -> None:
        # At exact equality the asset is expired (pending_expires_at <= now()).
        business_id = _make_business(migrated_engine)
        asset_id = _make_asset(migrated_engine, business_id, expires_in_hours=1)
        self._set_expiry(migrated_engine, asset_id, "now()")
        assert self._attachable(migrated_engine, business_id, asset_id) is False
