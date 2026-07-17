"""Business persistence access (M2B).

Repositories never commit (M2A/blueprint discipline): the businesses
service owns the transaction. Cross-tenant business queries here are
reachable only through services that first pass a platform capability
(``platform.businesses.manage``) — the platform-scope exception in
docs/04.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.businesses.models import Business


def add(db: Session, business: Business) -> None:
    db.add(business)


def get(db: Session, business_id: uuid.UUID) -> Business | None:
    return db.get(Business, business_id)


def get_for_update(db: Session, business_id: uuid.UUID) -> Business | None:
    """Load a business row with ``FOR UPDATE`` (serializes transitions)."""
    return db.execute(
        select(Business).where(Business.id == business_id).with_for_update()
    ).scalar_one_or_none()


def list_page(db: Session, *, limit: int, offset: int) -> tuple[list[Business], int]:
    """One bounded, deterministically ordered page plus the total count.

    Order is ``created_at DESC, id DESC`` — the ``id`` tiebreak makes the
    ordering total even when timestamps collide (approved point 7).
    """
    total = db.execute(select(func.count()).select_from(Business)).scalar_one()
    items = list(
        db.execute(
            select(Business)
            .order_by(Business.created_at.desc(), Business.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return items, int(total)
