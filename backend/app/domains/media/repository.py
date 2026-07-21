"""Media persistence access (M3C, ADR-017).

Every read of tenant-owned data takes ``business_id`` (docs/04). The
repository never commits (M2A discipline): the media service owns the
transaction and the Business row lock that serializes writes per tenant.

Quota usage is computed from **authoritative rows** under the lock via
two separate non-multiplying aggregates (final correction 1) — the asset
byte sum and the variant byte sum are summed independently, never through
a parent→child join that would multiply the canonical byte size once per
variant. There is no stored byte total to drift.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.media.models import MediaAsset, MediaAssetVariant


@dataclass(frozen=True)
class BusinessMediaUsage:
    """A business's authoritative media usage (pending + active)."""

    asset_count: int
    stored_bytes: int


def add(db: Session, entity: MediaAsset | MediaAssetVariant) -> None:
    db.add(entity)


def get_asset(db: Session, *, business_id: uuid.UUID, asset_id: uuid.UUID) -> MediaAsset | None:
    return db.execute(
        select(MediaAsset).where(MediaAsset.business_id == business_id, MediaAsset.id == asset_id)
    ).scalar_one_or_none()


def lock_asset(db: Session, *, business_id: uuid.UUID, asset_id: uuid.UUID) -> MediaAsset | None:
    """Row-lock one asset for a mutation (delete/attach) under the tenant lock."""
    return db.execute(
        select(MediaAsset)
        .where(MediaAsset.business_id == business_id, MediaAsset.id == asset_id)
        .with_for_update()
    ).scalar_one_or_none()


def list_assets(
    db: Session,
    *,
    business_id: uuid.UUID,
    limit: int,
    offset: int,
    status: str | None = None,
) -> list[MediaAsset]:
    """A page of assets, newest first (optional status filter)."""
    query = select(MediaAsset).where(MediaAsset.business_id == business_id)
    if status is not None:
        query = query.where(MediaAsset.status == status)
    query = query.order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
    return list(db.execute(query.limit(limit).offset(offset)).scalars())


def count_assets(db: Session, *, business_id: uuid.UUID, status: str | None = None) -> int:
    query = (
        select(func.count()).select_from(MediaAsset).where(MediaAsset.business_id == business_id)
    )
    if status is not None:
        query = query.where(MediaAsset.status == status)
    return int(db.execute(query).scalar_one())


def business_usage(db: Session, *, business_id: uuid.UUID) -> BusinessMediaUsage:
    """Authoritative count + stored bytes (two non-multiplying aggregates)."""
    asset_count = db.execute(
        select(func.count()).select_from(MediaAsset).where(MediaAsset.business_id == business_id)
    ).scalar_one()
    asset_bytes = db.execute(
        select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(
            MediaAsset.business_id == business_id
        )
    ).scalar_one()
    variant_bytes = db.execute(
        select(func.coalesce(func.sum(MediaAssetVariant.byte_size), 0)).where(
            MediaAssetVariant.business_id == business_id
        )
    ).scalar_one()
    return BusinessMediaUsage(
        asset_count=int(asset_count),
        stored_bytes=int(asset_bytes) + int(variant_bytes),
    )


def list_variants(
    db: Session, *, business_id: uuid.UUID, asset_id: uuid.UUID
) -> list[MediaAssetVariant]:
    return list(
        db.execute(
            select(MediaAssetVariant)
            .where(
                MediaAssetVariant.business_id == business_id,
                MediaAssetVariant.asset_id == asset_id,
            )
            .order_by(MediaAssetVariant.byte_size)
        ).scalars()
    )


def list_variants_for_assets(
    db: Session, *, business_id: uuid.UUID, asset_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MediaAssetVariant]]:
    """All (asset_id -> variants) for a page of assets."""
    if not asset_ids:
        return {}
    rows = db.execute(
        select(MediaAssetVariant)
        .where(
            MediaAssetVariant.business_id == business_id,
            MediaAssetVariant.asset_id.in_(asset_ids),
        )
        .order_by(MediaAssetVariant.asset_id, MediaAssetVariant.byte_size)
    ).scalars()
    by_asset: dict[uuid.UUID, list[MediaAssetVariant]] = {}
    for variant in rows:
        by_asset.setdefault(variant.asset_id, []).append(variant)
    return by_asset


def delete_asset(db: Session, asset: MediaAsset) -> None:
    db.delete(asset)


def list_expired_pending_after(
    db: Session, *, after_id: uuid.UUID | None, limit: int
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """One keyset batch of expired-pending (business_id, asset_id) pairs.

    Expiry is decided by the **database clock** (``func.now()``, final
    correction 4) — never an application timestamp, so clock skew on the
    operator host cannot change the decision. Ordered by ``id`` with a
    keyset cursor so the sweep processes bounded batches and terminates in
    both dry-run and apply modes (dry-run advances the cursor past rows it
    does not delete). Selected without locks; the sweep re-reads each
    candidate under the Business lock before acting.
    """
    query = select(MediaAsset.business_id, MediaAsset.id).where(
        MediaAsset.status == "pending",
        MediaAsset.pending_expires_at <= func.now(),
    )
    if after_id is not None:
        query = query.where(MediaAsset.id > after_id)
    rows = db.execute(query.order_by(MediaAsset.id).limit(limit)).all()
    return [(row[0], row[1]) for row in rows]


def list_assets_after(db: Session, *, after_id: uuid.UUID | None, limit: int) -> list[MediaAsset]:
    """One keyset batch of assets ordered by ``id`` (bounded inventory walk).

    Used by the missing-object report and backup verification instead of an
    unbounded ``.all()`` load (final correction 4).
    """
    query = select(MediaAsset)
    if after_id is not None:
        query = query.where(MediaAsset.id > after_id)
    return list(db.execute(query.order_by(MediaAsset.id).limit(limit)).scalars())
