"""Restaurant persistence access (M2B).

Repositories never commit (M2A/blueprint discipline): the tenants service
owns the transaction. Cross-tenant restaurant queries here are reachable
only through services that first pass a platform capability
(``platform.restaurants.manage``) — the platform-scope exception in
docs/04.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.tenants.models import Restaurant


def add(db: Session, restaurant: Restaurant) -> None:
    db.add(restaurant)


def get(db: Session, restaurant_id: uuid.UUID) -> Restaurant | None:
    return db.get(Restaurant, restaurant_id)


def get_for_update(db: Session, restaurant_id: uuid.UUID) -> Restaurant | None:
    """Load a restaurant row with ``FOR UPDATE`` (serializes transitions)."""
    return db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id).with_for_update()
    ).scalar_one_or_none()


def list_page(db: Session, *, limit: int, offset: int) -> tuple[list[Restaurant], int]:
    """One bounded, deterministically ordered page plus the total count.

    Order is ``created_at DESC, id DESC`` — the ``id`` tiebreak makes the
    ordering total even when timestamps collide (approved point 7).
    """
    total = db.execute(select(func.count()).select_from(Restaurant)).scalar_one()
    items = list(
        db.execute(
            select(Restaurant)
            .order_by(Restaurant.created_at.desc(), Restaurant.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return items, int(total)
