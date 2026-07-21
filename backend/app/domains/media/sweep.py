"""Media sweep: lifecycle-independent system maintenance (M3C, ADR-017).

Operator tooling (the ``sweep_media`` CLI wraps these functions). All
destructive actions are gated behind ``apply=True``; the default is a
dry run. The four categories (final correction K):

1. **Expired pending rows** — cleaned for ANY business lifecycle,
   including closed (system maintenance, not an owner mutation, final
   correction 4). Each candidate is re-read under the Business
   ``FOR UPDATE`` lock and re-checked on the database clock; a NULL-actor
   ``media.asset_expired`` event and the row deletion commit atomically;
   objects are deleted only after commit.
2. **Storage-only orphans** — an object with no corresponding asset row
   (canonical) or variant row (final correction 5), older than the 24 h
   safety age judged from storage last-modified metadata. Malformed or
   unknown-shape keys are report-only, never deleted.
3. **Rows without required objects** — report-only, always.
4. **Stale temporary files** — ``.tmp`` entries older than the safety age.

Reports carry business ids, asset ids, logical variants, and counts —
never internal keys or filesystem paths (final correction N).
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import MediaAssetExpiredDetails
from app.domains.businesses.queries import lock_business_status
from app.domains.media import policies, repository
from app.domains.media.models import MediaAsset, MediaAssetVariant
from app.domains.media.policies import CANONICAL_VARIANT
from app.domains.media.storage import (
    MaintenanceStorage,
    ObjectNotFoundError,
    object_key,
    parse_key,
)

# A defensive ceiling on the number of batch iterations, so a logic error
# (a cursor that fails to advance) can never spin forever.
_MAX_BATCHES = 1_000_000


@dataclass
class MissingObject:
    business_id: uuid.UUID
    asset_id: uuid.UUID
    variant: str


@dataclass
class SweepReport:
    apply: bool
    expired_pending_deleted: int = 0
    expired_object_delete_failures: int = 0
    orphans_deleted: int = 0
    orphans_too_young: int = 0
    orphan_delete_failures: int = 0
    malformed_keys: int = 0
    missing_objects: list[MissingObject] = field(default_factory=list)
    stale_temps_deleted: int = 0


def sweep_expired_pending(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    report: SweepReport,
    *,
    batch_size: int = 200,
) -> None:
    """Delete expired-pending assets across all businesses (see module doc).

    Bounded keyset batches (final correction 4): each pass loads at most
    ``batch_size`` candidates, advancing a cursor by ``id`` so the loop
    terminates in both dry-run and apply modes without an unbounded
    inventory load.
    """
    after_id: uuid.UUID | None = None
    for _ in range(_MAX_BATCHES):
        with session_factory() as db:
            candidates = repository.list_expired_pending_after(
                db, after_id=after_id, limit=batch_size
            )
        if not candidates:
            break
        after_id = candidates[-1][1]  # advance the cursor (even in dry-run)

        by_business: dict[uuid.UUID, list[uuid.UUID]] = {}
        for business_id, asset_id in candidates:
            by_business.setdefault(business_id, []).append(asset_id)

        for business_id, asset_ids in by_business.items():
            _sweep_business_expired(session_factory, storage, report, business_id, asset_ids)

        if len(candidates) < batch_size:
            break


def _sweep_business_expired(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    report: SweepReport,
    business_id: uuid.UUID,
    asset_ids: list[uuid.UUID],
) -> None:
    object_keys: list[str] = []
    with session_factory() as db:
        # Lock the Business row first (deterministic order); note we do NOT
        # reject closed businesses — expired-pending cleanup is
        # lifecycle-independent system maintenance (final correction 4).
        lock_business_status(db, business_id)
        deleted_here = 0
        for asset_id in asset_ids:
            asset = _relock_expired(db, business_id, asset_id)
            if asset is None:
                continue  # won the race elsewhere (attached/deleted/promoted)
            variant_names = [
                variant.variant
                for variant in repository.list_variants(
                    db, business_id=business_id, asset_id=asset_id
                )
            ]
            object_keys.append(object_key(business_id, asset_id, CANONICAL_VARIANT))
            object_keys += [object_key(business_id, asset_id, name) for name in variant_names]
            if report.apply:
                recorder.record(
                    db,
                    AuditAction.MEDIA_ASSET_EXPIRED,
                    actor_user_id=None,  # system attribution (NULL actor)
                    business_id=business_id,
                    target_type="media_asset",
                    target_id=str(asset_id),
                    details=MediaAssetExpiredDetails(
                        trigger="pending_ttl_sweep",
                        variant_count=len(variant_names),
                    ),
                )
                repository.delete_asset(db, asset)
            deleted_here += 1
        if report.apply:
            db.commit()
        report.expired_pending_deleted += deleted_here

    if report.apply:
        # Objects only after the row deletion committed; per-object isolation.
        for key in object_keys:
            try:
                storage.delete(key=key)
            except Exception:
                report.expired_object_delete_failures += 1


def _relock_expired(db: Session, business_id: uuid.UUID, asset_id: uuid.UUID) -> MediaAsset | None:
    """Re-read a candidate under the lock; return it only if still eligible.

    Eligible = still exists, still pending, and still expired on the
    database clock. An attach/delete/promotion that won the lock first has
    already changed or removed the row.
    """
    asset = db.execute(
        select(MediaAsset)
        .where(MediaAsset.business_id == business_id, MediaAsset.id == asset_id)
        .with_for_update()
    ).scalar_one_or_none()
    if asset is None or asset.status != "pending":
        return None
    still_expired = db.execute(
        select(MediaAsset.pending_expires_at <= func.now()).where(
            MediaAsset.business_id == business_id, MediaAsset.id == asset_id
        )
    ).scalar_one()
    return asset if still_expired else None


def sweep_orphans(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    report: SweepReport,
    *,
    safety_age_hours: int = policies.ORPHAN_SAFETY_AGE_HOURS,
) -> None:
    """Delete storage-only orphan objects older than the safety age."""
    cutoff_seconds = safety_age_hours * 3600
    for stat in storage.iter_objects():
        parsed = parse_key(stat.key)
        if parsed is None:
            report.malformed_keys += 1  # report-only; never deleted
            continue
        with session_factory() as db:
            expected = _object_is_expected(db, parsed.business_id, parsed.asset_id, parsed.variant)
        if expected:
            continue
        age_seconds = (datetime.now(UTC) - stat.last_modified).total_seconds()
        if age_seconds < cutoff_seconds:
            report.orphans_too_young += 1
            continue
        if report.apply:
            try:
                storage.delete(key=stat.key)
                report.orphans_deleted += 1
            except Exception:
                report.orphan_delete_failures += 1
        else:
            report.orphans_deleted += 1  # would-delete count in dry run


def _object_is_expected(
    db: Session, business_id: uuid.UUID, asset_id: uuid.UUID, variant: str
) -> bool:
    """An object is expected only as an existing asset's canonical or an
    existing variant row (final correction 5) — not merely because the
    asset row exists."""
    if variant == CANONICAL_VARIANT:
        return (
            db.execute(
                select(MediaAsset.id).where(
                    MediaAsset.business_id == business_id, MediaAsset.id == asset_id
                )
            ).scalar_one_or_none()
            is not None
        )
    return (
        db.execute(
            select(MediaAssetVariant.id).where(
                MediaAssetVariant.business_id == business_id,
                MediaAssetVariant.asset_id == asset_id,
                MediaAssetVariant.variant == variant,
            )
        ).scalar_one_or_none()
        is not None
    )


def report_missing_objects(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    report: SweepReport,
    *,
    batch_size: int = 200,
) -> None:
    """Report (never delete) asset/variant rows whose objects are absent.

    Bounded keyset walk (final correction 4): assets are read one batch at
    a time rather than loaded whole with ``.all()``.
    """
    after_id: uuid.UUID | None = None
    for _ in range(_MAX_BATCHES):
        with session_factory() as db:
            assets = repository.list_assets_after(db, after_id=after_id, limit=batch_size)
            batch: list[tuple[uuid.UUID, uuid.UUID, list[str]]] = [
                (
                    asset.business_id,
                    asset.id,
                    [
                        v.variant
                        for v in repository.list_variants(
                            db, business_id=asset.business_id, asset_id=asset.id
                        )
                    ],
                )
                for asset in assets
            ]
        if not batch:
            break
        after_id = batch[-1][1]
        for business_id, asset_id, variant_names in batch:
            for variant in (CANONICAL_VARIANT, *variant_names):
                if storage.stat(key=object_key(business_id, asset_id, variant)) is None:
                    report.missing_objects.append(
                        MissingObject(business_id=business_id, asset_id=asset_id, variant=variant)
                    )
        if len(batch) < batch_size:
            break


def cleanup_stale_temps(
    storage: MaintenanceStorage,
    report: SweepReport,
    *,
    safety_age_hours: int = policies.ORPHAN_SAFETY_AGE_HOURS,
) -> None:
    """Delete stale ``.tmp`` scratch files (apply); count them (dry run).

    Dry run reports the would-delete count without touching anything
    (final correction 4), consistent with the orphan would-delete count.
    """
    from app.domains.media.storage import LocalFilesystemStorage

    if not isinstance(storage, LocalFilesystemStorage):
        return
    if report.apply:
        report.stale_temps_deleted += storage.cleanup_stale_temps(older_than_hours=safety_age_hours)
    else:
        report.stale_temps_deleted += storage.count_stale_temps(older_than_hours=safety_age_hours)


def run_sweep(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    *,
    apply: bool,
    batch_size: int = 200,
) -> SweepReport:
    """Run all four sweep categories and return the combined report."""
    report = SweepReport(apply=apply)
    sweep_expired_pending(session_factory, storage, report, batch_size=batch_size)
    sweep_orphans(session_factory, storage, report)
    report_missing_objects(session_factory, storage, report, batch_size=batch_size)
    cleanup_stale_temps(storage, report)
    return report


# --- Backup verification (final correction 3) --------------------------------


@dataclass
class VerifyFinding:
    """One backup-consistency failure (never a key, path, or checksum value)."""

    business_id: uuid.UUID
    asset_id: uuid.UUID
    variant: str
    # 'missing' | 'size_mismatch' | 'checksum_mismatch' | 'orphan' | 'unreadable'
    kind: str


@dataclass
class VerifyReport:
    findings: list[VerifyFinding] = field(default_factory=list)
    malformed_keys: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings and self.malformed_keys == 0


def verify_backup(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    *,
    batch_size: int = 200,
) -> VerifyReport:
    """Backup preflight/verification — never mutates (final correction 3).

    Enumerates every expected canonical and variant object in bounded
    batches, comparing stored byte size and a recomputed SHA-256 against
    the database rows, then flags **every** storage-only object regardless
    of age (a quiesced backup set must have none). Malformed or unknown key
    shapes get an explicit non-success disposition (``malformed_keys``).
    Findings carry business id, asset id, and logical variant only — never
    a key, path, or checksum value.
    """
    report = VerifyReport()
    _verify_expected_objects(session_factory, storage, report, batch_size=batch_size)
    _verify_no_storage_only_objects(session_factory, storage, report)
    return report


def _verify_expected_objects(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    report: VerifyReport,
    *,
    batch_size: int,
) -> None:
    after_id: uuid.UUID | None = None
    for _ in range(_MAX_BATCHES):
        with session_factory() as db:
            assets = repository.list_assets_after(db, after_id=after_id, limit=batch_size)
            # (business_id, asset_id, variant, byte_size, checksum) tuples.
            expected: list[tuple[uuid.UUID, uuid.UUID, str, int, str]] = []
            for asset in assets:
                expected.append(
                    (
                        asset.business_id,
                        asset.id,
                        CANONICAL_VARIANT,
                        asset.byte_size,
                        asset.checksum_sha256,
                    )
                )
                for v in repository.list_variants(
                    db, business_id=asset.business_id, asset_id=asset.id
                ):
                    expected.append(
                        (asset.business_id, asset.id, v.variant, v.byte_size, v.checksum_sha256)
                    )
            last_id = assets[-1].id if assets else None
        if not expected and last_id is None:
            break
        for business_id, asset_id, variant, byte_size, checksum in expected:
            _verify_one_object(storage, report, business_id, asset_id, variant, byte_size, checksum)
        if last_id is None or len(assets) < batch_size:
            break
        after_id = last_id


def _verify_one_object(
    storage: MaintenanceStorage,
    report: VerifyReport,
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    variant: str,
    byte_size: int,
    checksum: str,
) -> None:
    """Verify one expected object, never letting a storage error escape.

    A missing object at either ``stat`` or ``open`` becomes a safe
    ``missing`` finding; any other stat/open/read failure becomes a safe
    ``unreadable`` finding (round-2 finding 3). No exception, key, path, or
    checksum value is ever surfaced — only the (business, asset, variant,
    kind) tuple.
    """
    key = object_key(business_id, asset_id, variant)

    def _finding(kind: str) -> None:
        report.findings.append(VerifyFinding(business_id, asset_id, variant, kind))

    try:
        stat = storage.stat(key=key)
    except ObjectNotFoundError:
        _finding("missing")
        return
    except Exception:
        _finding("unreadable")
        return
    if stat is None:
        _finding("missing")
        return
    if stat.byte_size != byte_size:
        _finding("size_mismatch")
        return

    digest = hashlib.sha256()
    try:
        with storage.open(key=key) as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except ObjectNotFoundError:
        _finding("missing")
        return
    except Exception:
        _finding("unreadable")
        return
    if digest.hexdigest() != checksum:
        _finding("checksum_mismatch")


def _verify_no_storage_only_objects(
    session_factory: sessionmaker[Session],
    storage: MaintenanceStorage,
    report: VerifyReport,
) -> None:
    for stat in storage.iter_objects():
        parsed = parse_key(stat.key)
        if parsed is None:
            report.malformed_keys += 1
            continue
        with session_factory() as db:
            expected = _object_is_expected(db, parsed.business_id, parsed.asset_id, parsed.variant)
        if not expected:
            # Any age: a quiesced backup set must have no storage-only object.
            report.findings.append(
                VerifyFinding(parsed.business_id, parsed.asset_id, parsed.variant, "orphan")
            )
