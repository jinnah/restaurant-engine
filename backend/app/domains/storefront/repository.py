"""Storefront persistence access (M4B, ADR-020).

Every read of tenant-owned data takes ``business_id`` (docs/04). The
repository never commits (M2A discipline): the storefront service owns
the transaction and the Business row lock that serializes writes per
tenant, so no query here needs its own row lock.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.storefront.models import StorefrontVersion, VersionState


def add(db: Session, version: StorefrontVersion) -> None:
    db.add(version)


def get_draft(db: Session, *, business_id: uuid.UUID) -> StorefrontVersion | None:
    """The singleton mutable draft, or ``None`` (valid first-use absence)."""
    return db.execute(
        select(StorefrontVersion).where(
            StorefrontVersion.business_id == business_id,
            StorefrontVersion.state == VersionState.DRAFT.value,
        )
    ).scalar_one_or_none()


def get_published(db: Session, *, business_id: uuid.UUID) -> StorefrontVersion | None:
    """The at-most-one currently published version."""
    return db.execute(
        select(StorefrontVersion).where(
            StorefrontVersion.business_id == business_id,
            StorefrontVersion.state == VersionState.PUBLISHED.value,
        )
    ).scalar_one_or_none()


def get_version(
    db: Session, *, business_id: uuid.UUID, version_id: uuid.UUID
) -> StorefrontVersion | None:
    """One version row by tenant-scoped id, in any state.

    Unknown and cross-tenant ids are the same ``None`` — the caller renders
    both as the indistinguishable 404 (docs/04). State legality (history
    reads exclude the draft; restore accepts archived only) is the
    service's decision, not a query predicate here.
    """
    return db.execute(
        select(StorefrontVersion).where(
            StorefrontVersion.business_id == business_id,
            StorefrontVersion.id == version_id,
        )
    ).scalar_one_or_none()


def list_history(
    db: Session, *, business_id: uuid.UUID, limit: int, offset: int
) -> list[StorefrontVersion]:
    """One history page: published + archived, newest version first.

    The predicate is the **literal** ``version_number IS NOT NULL`` — the
    exact form the partial history index declares. PostgreSQL considers a
    partial index only when the query implies its predicate literally, and
    its prover does not consult CHECK constraints, so the logically
    identical ``state <> 'draft'`` falls back to a sequential scan
    (measured; see the index comment in ``models.py``).
    """
    return list(
        db.execute(
            select(StorefrontVersion)
            .where(
                StorefrontVersion.business_id == business_id,
                StorefrontVersion.version_number.is_not(None),
            )
            .order_by(StorefrontVersion.version_number.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )


def count_history(db: Session, *, business_id: uuid.UUID) -> int:
    """Total history rows (published + archived), for the page envelope."""
    return int(
        db.execute(
            select(func.count())
            .select_from(StorefrontVersion)
            .where(
                StorefrontVersion.business_id == business_id,
                StorefrontVersion.version_number.is_not(None),
            )
        ).scalar_one()
    )


def next_version_number(db: Session, *, business_id: uuid.UUID) -> int:
    """The next version number to mint, under the caller's Business lock.

    ``max + 1`` over the numbered rows only (the literal partial-index
    predicate again). Version numbers are minted exclusively at
    publication (ADR-020 §4), so the sequence is dense per business and
    race-free under the lock.
    """
    current = db.execute(
        select(func.max(StorefrontVersion.version_number)).where(
            StorefrontVersion.business_id == business_id,
            StorefrontVersion.version_number.is_not(None),
        )
    ).scalar_one()
    return int(current or 0) + 1
