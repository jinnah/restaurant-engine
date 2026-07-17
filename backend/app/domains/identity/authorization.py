"""Membership-backed authorization helper (M2B).

Identity owns memberships and the capability policy, so the DB-backed
membership check lives here (it needs a database lookup, unlike the pure
``policies.require_platform_capability``). Any business-scoped service
calls this before doing work — enforcement is in the service layer, never
only in an HTTP dependency (approved decision 4).

Failure semantics (docs/04, approved point 5):

* no membership row (nonexistent business OR not a member) →
  ``ResourceNotFoundError`` (404), so existence is not disclosed;
* member whose role lacks the capability → ``PermissionDeniedError`` (403).
"""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError, ResourceNotFoundError
from app.domains.identity import memberships
from app.domains.identity.actor import ActorContext
from app.domains.identity.policies import Capability, Role, role_has_capability


def require_membership_capability(
    db: Session,
    actor: ActorContext,
    *,
    business_id: uuid.UUID,
    capability: Capability,
) -> Role:
    """Authorize a business-scoped action; return the actor's role.

    Platform admins are **not** implicitly members (approved decision): a
    platform admin with no membership row is a nonmember here and gets 404,
    exactly like any other nonmember. Platform-scoped access uses the
    platform routes and ``require_platform_capability`` instead.
    """
    role = memberships.get_role(db, business_id=business_id, user_id=actor.user.id)
    if role is None:
        raise ResourceNotFoundError("Business not found.")
    if not role_has_capability(role, capability):
        raise PermissionDeniedError()
    return role
