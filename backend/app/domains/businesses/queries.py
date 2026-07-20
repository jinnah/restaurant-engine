"""Business read models for cross-domain composition (M2B).

Published, businesses-owned read surface used by the application
composition layer to enrich the session projection (addendum decision 4).
Returns plain value objects — never ORM instances — so no consumer binds
to persistence. This module imports nothing from identity; the composition
layer joins the two domains' read models itself.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.businesses.models import Business


@dataclass(frozen=True)
class BusinessSummaryView:
    """The tenant facts the session projection needs about one business."""

    slug: str
    name: str
    status: str


def lock_business_status(db: Session, business_id: uuid.UUID) -> str | None:
    """Lock the business row (``FOR UPDATE``) and return its status (M3A).

    The businesses-owned serialization point other domains' write services
    use: catalog mutations lock the Business row **first** (deterministic
    lock order, ADR-014/ADR-017), which both serializes per-tenant catalog
    writes (making count-limit checks race-safe) and pins the lifecycle
    status for the transaction. Returns ``None`` for a nonexistent
    business. Never commits — the calling service owns the transaction.
    """
    return db.execute(
        select(Business.status).where(Business.id == business_id).with_for_update()
    ).scalar_one_or_none()


def get_business_summaries(
    db: Session, business_ids: list[uuid.UUID]
) -> dict[uuid.UUID, BusinessSummaryView]:
    """Map the given business ids to their summary facts (keyed lookup)."""
    if not business_ids:
        return {}
    rows = db.execute(
        select(Business.id, Business.slug, Business.name, Business.status).where(
            Business.id.in_(business_ids)
        )
    ).all()
    return {
        row_id: BusinessSummaryView(slug=slug, name=name, status=status)
        for row_id, slug, name, status in rows
    }
