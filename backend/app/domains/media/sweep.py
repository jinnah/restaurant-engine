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
from app.domains.media.storage import MaintenanceStorage, object_key, parse_key


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
    """Delete expired-pending assets across all businesses (see module doc)."""
    with session_factory() as db:
        candidates = repository.get_expired_pending_ids(db, now=datetime.now(UTC), limit=batch_size)
    # Group by business so each business is handled under one lock.
    by_business: dict[uuid.UUID, list[uuid.UUID]] = {}
    for business_id, asset_id in candidates:
        by_business.setdefault(business_id, []).append(asset_id)

    for business_id, asset_ids in by_business.items():
        object_keys: list[str] = []
        with session_factory() as db:
            # Lock the Business row first (deterministic order); note we do
            # NOT reject closed businesses — expired-pending cleanup is
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
            # Objects only after the row deletion committed.
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
) -> None:
    """Report (never delete) asset/variant rows whose objects are absent."""
    with session_factory() as db:
        assets = db.execute(select(MediaAsset)).scalars().all()
        for asset in assets:
            expected = [(asset.business_id, asset.id, CANONICAL_VARIANT)]
            variants = repository.list_variants(
                db, business_id=asset.business_id, asset_id=asset.id
            )
            expected += [(asset.business_id, asset.id, v.variant) for v in variants]
            for business_id, asset_id, variant in expected:
                if storage.stat(key=object_key(business_id, asset_id, variant)) is None:
                    report.missing_objects.append(
                        MissingObject(business_id=business_id, asset_id=asset_id, variant=variant)
                    )


def cleanup_stale_temps(
    storage: MaintenanceStorage,
    report: SweepReport,
    *,
    safety_age_hours: int = policies.ORPHAN_SAFETY_AGE_HOURS,
) -> None:
    """Delete stale ``.tmp`` scratch files (apply mode only)."""
    from app.domains.media.storage import LocalFilesystemStorage

    if report.apply and isinstance(storage, LocalFilesystemStorage):
        report.stale_temps_deleted += storage.cleanup_stale_temps(older_than_hours=safety_age_hours)


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
    report_missing_objects(session_factory, storage, report)
    cleanup_stale_temps(storage, report)
    return report
