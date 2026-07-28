"""Shared storefront service internals (M4B, ADR-020).

The authorization preamble and transaction-boundary error conversion for
the storefront domain — the catalog/media `service_support` pattern.
Storefront depends on core, identity, businesses, and media non-model
surfaces, never on catalog: menu content is referenced only through ids
the public projection resolves at render time.

Every storefront mutation runs the same preamble: membership capability
(404 nonmember / 403 missing capability), then the businesses-owned
Business ``FOR UPDATE`` row lock — the deterministic first lock (ADR-020
§5.8) that serializes every storefront write per tenant, including the
first-draft creation race — then the lifecycle gate (closed businesses
are immutable, §8). Repositories never commit; the calling service owns
the transaction and uses ``safe_flush``/``safe_commit`` so a known
integrity violation converts to a stable 409 while an unknown failure
still propagates to the opaque internal-error boundary. Under the
Business lock the storefront singletons cannot actually race — the
conversion is belt-and-braces, not the invariant.
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

# Friendly messages for the storefront singleton/numbering uniques. The
# Business row lock makes these unreachable through the service; a direct
# or future path that races them still gets a safe 409, never a 500.
CONFLICT_CONSTRAINTS: dict[str, str] = {
    "uq_storefront_versions_one_draft": "a draft already exists for this business",
    "uq_storefront_versions_one_published": (
        "a published version already exists for this business"
    ),
    "uq_storefront_versions_business_id_version_number": "version numbering conflicted; retry",
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
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = constraint_message(exc)
        if message is not None:
            raise ConflictError(message) from None
        raise


def authorize_read(db: Session, actor: ActorContext, business_id: uuid.UUID) -> None:
    """Storefront reads require ``business.storefront.read`` (ADR-020 §7).

    Broad ``business.view`` is deliberately insufficient for any storefront
    administration read, so staff — members who hold ``business.view`` —
    receive 403 here rather than a view of the composition.
    """
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_STOREFRONT_READ
    )


def authorize_write(
    db: Session, actor: ActorContext, business_id: uuid.UUID, capability: Capability
) -> None:
    """Capability, Business lock, and lifecycle — the write preamble.

    ``capability`` is ``business.storefront.write`` for draft mutations and
    ``business.storefront.publish`` for publication and restoration (owner
    only, §7 — one capability deliberately covers both commands).
    """
    require_membership_capability(db, actor, business_id=business_id, capability=capability)
    status = lock_business_status(db, business_id)
    if status is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    if status == BusinessStatus.CLOSED.value:
        raise InvalidStateError("cannot modify the storefront of a closed business")
