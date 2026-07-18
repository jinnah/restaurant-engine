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
    """Named capabilities enforced in M2B/M2D.

    Append-only, like the error and audit registries: capabilities are
    added in the change that first enforces them.
    """

    # Platform-scoped (conferred by is_platform_admin).
    PLATFORM_BUSINESSES_MANAGE = "platform.businesses.manage"
    # Account recovery is account-takeover-equivalent authority (ADR-014):
    # audited on every issuance, and there is no public issuance path.
    PLATFORM_USERS_RECOVER = "platform.users.recover"
    PLATFORM_AUDIT_READ = "platform.audit.read"
    # Business-scoped (conferred by a membership role).
    BUSINESS_VIEW = "business.view"
    BUSINESS_MEMBERS_INVITE = "business.members.invite"
    BUSINESS_AUDIT_READ = "business.audit.read"


PLATFORM_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.PLATFORM_BUSINESSES_MANAGE,
        Capability.PLATFORM_USERS_RECOVER,
        Capability.PLATFORM_AUDIT_READ,
    }
)

# Every role maps to a capability set; every business role can view its
# business. Owners and managers may invite members and read the business
# audit trail (ADR-014 rulings); staff may not.
CAPABILITIES_BY_ROLE: dict[Role, frozenset[Capability]] = {
    Role.OWNER: frozenset(
        {
            Capability.BUSINESS_VIEW,
            Capability.BUSINESS_MEMBERS_INVITE,
            Capability.BUSINESS_AUDIT_READ,
        }
    ),
    Role.MANAGER: frozenset(
        {
            Capability.BUSINESS_VIEW,
            Capability.BUSINESS_MEMBERS_INVITE,
            Capability.BUSINESS_AUDIT_READ,
        }
    ),
    Role.STAFF: frozenset({Capability.BUSINESS_VIEW}),
}

# Rank order for the invitation role ceiling (ADR-014): an actor may only
# issue, replace, or revoke an invitation whose role does not outrank their
# own. Platform administrators bypass rank through the platform route only.
_ROLE_RANK: dict[Role, int] = {Role.OWNER: 3, Role.MANAGER: 2, Role.STAFF: 1}


def role_outranks(role: Role, other: Role) -> bool:
    """True when ``role`` strictly outranks ``other``."""
    return _ROLE_RANK[role] > _ROLE_RANK[other]


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
