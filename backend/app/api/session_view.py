"""Enriched session view — application-level composition (M2B, decision 4).

The enriched ``auth_session`` response joins identity-owned memberships with
tenant-owned restaurant summaries. Neither domain owns this cross-join, so
it lives in the application/API composition layer: this module depends on
both domains; neither domain depends on the other for it, keeping the graph
acyclic (``app/api → identity + tenants``; ``tenants → identity``;
``identity → core``).

login stays lean (``SessionResponse`` = user + csrf token, identity-only);
this enriched ``SessionView`` is what ``GET /auth/session`` returns.
"""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domains.identity import memberships
from app.domains.identity.actor import ActorContext
from app.domains.identity.schemas import UserSummary
from app.domains.tenants import queries


class MembershipSummary(BaseModel):
    """One of the caller's restaurant memberships (composed projection)."""

    restaurant_id: str
    restaurant_slug: str
    restaurant_name: str
    role: str
    restaurant_status: str


class SessionView(BaseModel):
    """Current identity, CSRF token, and the caller's memberships.

    Superset of the login ``SessionResponse``: adds ``memberships``.
    Platform admins hold no memberships, so their list is empty.
    """

    user: UserSummary
    csrf_token: str
    memberships: list[MembershipSummary]


def build_session_view(db: Session, actor: ActorContext) -> SessionView:
    """Compose the enriched session for the authenticated actor.

    Membership listing is bound to the actor's own id (never a supplied id).
    The final projection is sorted ``restaurant_name ASC, restaurant_id ASC``
    (approved addendum decision 2) — the sort lives here, in the composition
    layer, since identity returns tenant-independent data only.
    """
    user_memberships = memberships.list_for_user(db, user_id=actor.user.id)
    summaries = queries.get_restaurant_summaries(db, [m.restaurant_id for m in user_memberships])

    projected: list[MembershipSummary] = []
    for membership in user_memberships:
        summary = summaries.get(membership.restaurant_id)
        if summary is None:  # pragma: no cover - FK guarantees the row exists
            continue
        projected.append(
            MembershipSummary(
                restaurant_id=str(membership.restaurant_id),
                restaurant_slug=summary.slug,
                restaurant_name=summary.name,
                role=membership.role.value,
                restaurant_status=summary.status,
            )
        )
    projected.sort(key=lambda m: (m.restaurant_name, m.restaurant_id))

    return SessionView(
        user=UserSummary(
            id=actor.user.id,
            email=actor.user.email,
            display_name=actor.user.display_name,
            is_platform_admin=actor.user.is_platform_admin,
        ),
        csrf_token=actor.csrf_token,
        memberships=projected,
    )
