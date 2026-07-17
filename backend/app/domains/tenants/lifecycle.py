"""Restaurant lifecycle state machine (M2B, blueprint §7.2).

    provisioning → active → suspended → active
                             └────────→ closed

Closure is reachable **only** through ``suspended → closed`` (approved
ruling 1): ``active`` cannot close directly. ``closed`` is terminal.
Transition legality lives here — not in a database CHECK, which cannot see
the previous value, and not in a trigger, which would hide business logic
in the database.
"""

from enum import StrEnum


class RestaurantStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


# For each status, the set of statuses it may transition to.
_ALLOWED: dict[RestaurantStatus, frozenset[RestaurantStatus]] = {
    RestaurantStatus.PROVISIONING: frozenset({RestaurantStatus.ACTIVE}),
    RestaurantStatus.ACTIVE: frozenset({RestaurantStatus.SUSPENDED}),
    RestaurantStatus.SUSPENDED: frozenset({RestaurantStatus.ACTIVE, RestaurantStatus.CLOSED}),
    RestaurantStatus.CLOSED: frozenset(),
}


def can_transition(current: RestaurantStatus, target: RestaurantStatus) -> bool:
    """True when ``current → target`` is a legal transition."""
    return target in _ALLOWED[current]
