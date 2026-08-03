"""Order status machine (blueprint §7.7; M6A, ADR-026).

The full §7.7 vocabulary ships now so the persisted status domain is
stable before M7 implements the member transitions — but Milestone 6 can
*produce* only ``SUBMITTED`` (placement) and ``CANCELLED`` (the customer
cancellation, ruling D11). Every other transition is M7's guarded command
surface; nothing in M6 writes them, and a permanent test pins that.

Status is never an arbitrary string patched by a generic endpoint: every
change is a named command that validates the current state, appends an
``order_status_events`` row, and audits, in one transaction.
"""

from enum import StrEnum


class OrderStatus(StrEnum):
    """The closed §7.7 status vocabulary (append-only)."""

    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# The only statuses Milestone 6 code could write (ruling D11-M6). M7A
# widens production to the full vocabulary through the named member
# commands below; the pinned test moved with it (ADR-027).
M6_PRODUCIBLE_STATUSES = frozenset({OrderStatus.SUBMITTED, OrderStatus.CANCELLED})

# The §7.7 machine as data (M7A, ADR-027 ruling D1): each named member
# command is legal from exactly one state and lands in exactly one.
# Commands are the ONLY write path — status is never patched.
MEMBER_TRANSITIONS: dict[str, tuple[OrderStatus, OrderStatus]] = {
    "accept": (OrderStatus.SUBMITTED, OrderStatus.ACCEPTED),
    "reject": (OrderStatus.SUBMITTED, OrderStatus.REJECTED),
    "start-preparing": (OrderStatus.ACCEPTED, OrderStatus.PREPARING),
    "mark-ready": (OrderStatus.PREPARING, OrderStatus.READY),
    "complete": (OrderStatus.READY, OrderStatus.COMPLETED),
    # Ruling D4: the machine's one path to cancelled, walkable by a
    # member for the phoned "please cancel" case. No new edges.
    "cancel": (OrderStatus.SUBMITTED, OrderStatus.CANCELLED),
}

# Statuses that release a claimed pickup slot (ruling D3): the D3-M6
# throttle count excludes these — a refused order occupies no capacity.
SLOT_RELEASING_STATUSES = frozenset({OrderStatus.CANCELLED, OrderStatus.REJECTED})

# The estimate is legal only while the kitchen owns the order (D7).
ESTIMATE_LEGAL_STATUSES = frozenset({OrderStatus.ACCEPTED, OrderStatus.PREPARING})


class PickupKind(StrEnum):
    """How the pickup promise was chosen at placement."""

    ASAP = "asap"
    SCHEDULED = "scheduled"


class StatusActorKind(StrEnum):
    """Who effected a status transition (the event row's actor facet)."""

    CUSTOMER = "customer"
    MEMBER = "member"
    SYSTEM = "system"
