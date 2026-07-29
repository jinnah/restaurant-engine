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


def read_business_status(db: Session, business_id: uuid.UUID) -> str | None:
    """Read a business status WITHOUT locking (M3C pre-body gate).

    The media upload flow validates the mutation lifecycle before parsing
    the request body (ADR-017 upload correction), where taking the
    ``FOR UPDATE`` lock is both premature and undesirable. The authoritative
    re-check under the lock still happens in the final transaction via
    ``lock_business_status``. Returns ``None`` for a nonexistent business.
    """
    return db.execute(
        select(Business.status).where(Business.id == business_id)
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


@dataclass(frozen=True)
class PublicSiteFacts:
    """The four public site facts of one business (the ADR-013 shape).

    Exactly the fields the public ``PublicSiteSummary`` projection carries
    — used by the authenticated storefront preview (M4C) so its response
    matches the public projection's shape. Carries no status: the preview
    caller has already passed a membership check, and the public surface
    derives these facts from Host resolution instead.
    """

    slug: str
    name: str
    timezone: str
    currency: str


def read_public_site_facts(db: Session, business_id: uuid.UUID) -> PublicSiteFacts | None:
    """The public site facts for one business id, or ``None`` if unknown.

    A lookup on the tenant root by its own primary key — a "which tenant"
    query, not a tenant-owned-data read (docs/04). Status is deliberately
    not filtered: the caller owns its authorization (the storefront
    preview runs behind a membership capability), and suspension must not
    hide a business from its own members.
    """
    row = db.execute(
        select(Business.slug, Business.name, Business.timezone, Business.currency).where(
            Business.id == business_id
        )
    ).one_or_none()
    if row is None:
        return None
    slug, name, timezone, currency = row
    return PublicSiteFacts(slug=slug, name=name, timezone=timezone, currency=currency)
