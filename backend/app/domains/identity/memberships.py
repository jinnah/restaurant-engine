"""Membership persistence access and read models (M2B).

Identity owns memberships (blueprint §7.1). These functions are the
tenant-scoped access surface other domains and the composition layer use;
they never commit (services own transactions, M2A discipline).

Tenant-scoping rule (docs/04): tenant-owned reads take ``business_id``.
The one sanctioned exception is ``list_for_user``, which is **self-scoped**
— bound to the authenticated actor's own ``user_id`` and spanning that
user's tenants — the same self/session exception class as session-token
resolution. It returns tenant-independent data only (business id + role);
the application layer enriches and sorts it (addendum decision 2).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.identity.models import Membership
from app.domains.identity.policies import Role


@dataclass(frozen=True)
class UserMembership:
    """Tenant-independent membership fact for one user (self-scoped read)."""

    business_id: uuid.UUID
    role: Role


def get_role(db: Session, *, business_id: uuid.UUID, user_id: uuid.UUID) -> Role | None:
    """The user's role in the given business, or None if not a member."""
    value = db.execute(
        select(Membership.role).where(
            Membership.business_id == business_id,
            Membership.user_id == user_id,
        )
    ).scalar_one_or_none()
    return Role(value) if value is not None else None


def count_owners(db: Session, *, business_id: uuid.UUID) -> int:
    """Number of owner memberships for a business (activation guard)."""
    count = db.execute(
        select(func.count())
        .select_from(Membership)
        .where(Membership.business_id == business_id, Membership.role == Role.OWNER.value)
    ).scalar_one()
    return int(count)


def list_for_user(db: Session, *, user_id: uuid.UUID) -> list[UserMembership]:
    """All of one user's memberships, tenant-independent (self-scoped).

    Ordering and business enrichment are the application layer's job; this
    returns raw facts in a stable id order only so the result is
    deterministic before enrichment.
    """
    rows = db.execute(
        select(Membership.business_id, Membership.role)
        .where(Membership.user_id == user_id)
        .order_by(Membership.business_id)
    ).all()
    return [UserMembership(business_id=bid, role=Role(role)) for bid, role in rows]
