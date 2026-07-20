"""Shared catalog service internals (M3B, ADR-017 D10 service-file ruling).

The authorization preamble, transaction-boundary error conversion, and
the single known-conflict constraint map — **moved** here from
``catalog.service`` so the M3A workflows (``service``) and the M3B
modifier workflows (``modifier_service``) share one implementation and
can never drift. This module imports only core, identity, and
businesses non-model surfaces; neither service module imports the other,
so the domain graph stays acyclic.

Repositories never commit; the calling service owns the transaction and
uses ``safe_flush``/``safe_commit`` so known uniqueness violations —
including the DEFERRED position constraints that can only surface at
commit — convert to stable 409 responses, while unknown integrity
failures still propagate to the opaque internal-error boundary.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidStateError, ResourceNotFoundError
from app.domains.businesses.lifecycle import BusinessStatus
from app.domains.businesses.queries import lock_business_status
from app.domains.identity.actor import ActorContext
from app.domains.identity.authorization import require_membership_capability
from app.domains.identity.policies import Capability

# Friendly messages for known uniqueness violations; anything else is a real
# error and propagates (the businesses-service conversion pattern). The
# position uniques are DEFERRED, so they can only surface at commit — a
# service logic error, still converted safely rather than leaked as a 500.
CONFLICT_CONSTRAINTS: dict[str, str] = {
    "uq_menu_categories_name_ci": "a category with this name already exists",
    "uq_menu_items_name_ci": "an item with this name already exists in this category",
    "uq_menu_categories_business_id_position": "category ordering conflicted; retry",
    "uq_menu_items_business_id_category_id_position": "item ordering conflicted; retry",
    "uq_menu_item_dietary_tags_business_id_item_id_tag": "duplicate dietary tag",
    # M3B modifiers.
    "uq_modifier_groups_name_ci": "a modifier group with this name already exists on this item",
    "uq_modifier_options_name_ci": "an option with this name already exists in this group",
    "uq_modifier_groups_business_id_item_id_position": "modifier group ordering conflicted; retry",
    "uq_modifier_options_business_id_group_id_position": "option ordering conflicted; retry",
}


def constraint_message(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return CONFLICT_CONSTRAINTS.get(name) if name is not None else None


def safe_flush(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        message = constraint_message(exc)
        if message is not None:
            raise ConflictError(message) from None
        raise


def safe_commit(db: Session) -> None:
    """Commit, converting deferred-constraint races to the same safe 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = constraint_message(exc)
        if message is not None:
            raise ConflictError(message) from None
        raise


def authorize_read(db: Session, actor: ActorContext, business_id: uuid.UUID) -> None:
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_VIEW
    )


def authorize_write(
    db: Session, actor: ActorContext, business_id: uuid.UUID, capability: Capability
) -> None:
    """Capability, business lock, and lifecycle — the write preamble.

    The Business row is the deterministic first (and only) lock for every
    catalog mutation: it serializes per-tenant writes, makes count-limit
    checks race-safe, and pins the lifecycle status (closed businesses are
    immutable, D8).
    """
    require_membership_capability(db, actor, business_id=business_id, capability=capability)
    status = lock_business_status(db, business_id)
    if status is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    if status == BusinessStatus.CLOSED.value:
        raise InvalidStateError("cannot modify the catalog of a closed business")
