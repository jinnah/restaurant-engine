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


# The only statuses Milestone 6 code may write (ruling D11). M7 widens
# this set when the member commands arrive; the pinned test moves with it.
M6_PRODUCIBLE_STATUSES = frozenset({OrderStatus.SUBMITTED, OrderStatus.CANCELLED})


class PickupKind(StrEnum):
    """How the pickup promise was chosen at placement."""

    ASAP = "asap"
    SCHEDULED = "scheduled"


class StatusActorKind(StrEnum):
    """Who effected a status transition (the event row's actor facet)."""

    CUSTOMER = "customer"
    MEMBER = "member"
    SYSTEM = "system"
