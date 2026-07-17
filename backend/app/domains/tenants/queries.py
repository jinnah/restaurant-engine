"""Tenant read models for cross-domain composition (M2B).

Published, tenants-owned read surface used by the application composition
layer to enrich the session projection (addendum decision 4). Returns plain
value objects — never ORM instances — so no consumer binds to persistence.
This module imports nothing from identity; the composition layer joins the
two domains' read models itself.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.tenants.models import Restaurant


@dataclass(frozen=True)
class RestaurantSummaryView:
    """The tenant facts the session projection needs about one restaurant."""

    slug: str
    name: str
    status: str


def get_restaurant_summaries(
    db: Session, restaurant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, RestaurantSummaryView]:
    """Map the given restaurant ids to their summary facts (keyed lookup)."""
    if not restaurant_ids:
        return {}
    rows = db.execute(
        select(Restaurant.id, Restaurant.slug, Restaurant.name, Restaurant.status).where(
            Restaurant.id.in_(restaurant_ids)
        )
    ).all()
    return {
        row_id: RestaurantSummaryView(slug=slug, name=name, status=status)
        for row_id, slug, name, status in rows
    }
