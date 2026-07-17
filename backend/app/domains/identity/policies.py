"""Capability authorization policy (M2B).

The one policy module (blueprint §7.1): identity owns roles and the
role-to-capability mapping. Authorization is expressed as named
capabilities, never scattered role-string comparisons.

Two kinds of authority, deliberately separate (approved M2B decision):

* **Platform capabilities** are conferred by the ``users.is_platform_admin``
  flag — never by a business membership. A platform admin holds no
  membership rows.
* **Business capabilities** are conferred by a membership ``role`` in a
  specific business.

This module is pure: it depends only on the actor and these constants, never
on the database or on the businesses domain. The membership-backed helper
that needs a database lookup lives in ``identity.authorization``.
"""

from enum import StrEnum

from app.core.errors import PermissionDeniedError
from app.domains.identity.actor import ActorContext


class Role(StrEnum):
    """Business membership roles (blueprint §7.1)."""

    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"


class Capability(StrEnum):
    """Named capabilities enforced in M2B.

    Append-only, like the error and audit registries: capabilities are
    added in the change that first enforces them. M2B enforces exactly two
    — catalog/order/entitlement capabilities arrive with their milestones.
    """

    # Platform-scoped (conferred by is_platform_admin).
    PLATFORM_BUSINESSES_MANAGE = "platform.businesses.manage"
    # Business-scoped (conferred by a membership role).
    BUSINESS_VIEW = "business.view"


PLATFORM_CAPABILITIES: frozenset[Capability] = frozenset({Capability.PLATFORM_BUSINESSES_MANAGE})

# Every role maps to a capability set; every business role can view its
# business. No role differentiates further in M2B (no catalog/order
# surface exists yet), so the map is deliberately uniform here.
CAPABILITIES_BY_ROLE: dict[Role, frozenset[Capability]] = {
    Role.OWNER: frozenset({Capability.BUSINESS_VIEW}),
    Role.MANAGER: frozenset({Capability.BUSINESS_VIEW}),
    Role.STAFF: frozenset({Capability.BUSINESS_VIEW}),
}


def role_has_capability(role: Role, capability: Capability) -> bool:
    """True when a business role confers the capability."""
    return capability in CAPABILITIES_BY_ROLE[role]


def require_platform_capability(actor: ActorContext, capability: Capability) -> None:
    """Enforce a platform capability, conferred only by is_platform_admin.

    Raises ``PermissionDeniedError`` (403) for any actor without the flag —
    including a business owner, who is a member but not a platform admin.
    Never grants via membership.
    """
    if capability not in PLATFORM_CAPABILITIES:
        # Defensive: platform capabilities are a closed set; asking for a
        # non-platform capability here is a programming error, not an
        # authorization outcome.
        msg = f"{capability!r} is not a platform capability"
        raise ValueError(msg)
    if not actor.user.is_platform_admin:
        raise PermissionDeniedError()
