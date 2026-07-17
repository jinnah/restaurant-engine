"""Business lifecycle state machine (M2B, blueprint §7.2).

    provisioning → active → suspended → active
                             └────────→ closed

Closure is reachable **only** through ``suspended → closed`` (approved
ruling 1): ``active`` cannot close directly. ``closed`` is terminal.
Transition legality lives here — not in a database CHECK, which cannot see
the previous value, and not in a trigger, which would hide domain logic
in the database.
"""

from enum import StrEnum


class BusinessStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


# For each status, the set of statuses it may transition to.
_ALLOWED: dict[BusinessStatus, frozenset[BusinessStatus]] = {
    BusinessStatus.PROVISIONING: frozenset({BusinessStatus.ACTIVE}),
    BusinessStatus.ACTIVE: frozenset({BusinessStatus.SUSPENDED}),
    BusinessStatus.SUSPENDED: frozenset({BusinessStatus.ACTIVE, BusinessStatus.CLOSED}),
    BusinessStatus.CLOSED: frozenset(),
}


def can_transition(current: BusinessStatus, target: BusinessStatus) -> bool:
    """True when ``current → target`` is a legal transition."""
    return target in _ALLOWED[current]
