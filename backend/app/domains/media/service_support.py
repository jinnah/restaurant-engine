"""Shared media service internals (M3C, ADR-017).

The authorization preamble and transaction-boundary error conversion for
the media domain. Media depends only on core, identity, and businesses
non-model surfaces — never on catalog (the acyclic graph, final
correction M): a referenced-asset deletion is caught by the named
``menu_items`` RESTRICT foreign key and mapped here, not by a reverse
lookup into the catalog domain.

Repositories never commit; the calling service owns the transaction and
uses ``safe_flush``/``safe_commit`` so a known integrity violation
converts to a stable 409, while an unknown failure still propagates to
the opaque internal-error boundary.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    ConflictError,
    InvalidStateError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.domains.businesses.lifecycle import BusinessStatus
from app.domains.businesses.queries import lock_business_status, read_business_status
from app.domains.identity import memberships
from app.domains.identity.actor import ActorContext
from app.domains.identity.authorization import require_membership_capability
from app.domains.identity.policies import Capability, role_has_capability

# A referenced asset cannot be deleted: the menu_items composite RESTRICT
# FK is the invariant; the service precheck only improves the message.
CONFLICT_CONSTRAINTS: dict[str, str] = {
    "fk_menu_items_business_id_image_media_id_media_assets": (
        "this image is in use by a menu item and cannot be deleted"
    ),
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
    """Any member may read/list/preview media (staff included, D4)."""
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_VIEW
    )


def authorize_write_nonlocking(db: Session, actor: ActorContext, business_id: uuid.UUID) -> None:
    """The pre-body gate (final correction F): capability + lifecycle, NO lock.

    Runs before any request body is parsed. Closed businesses are rejected
    here — a closed business's upload body is never parsed or processed.
    The authoritative re-check under the Business ``FOR UPDATE`` lock still
    happens in the final transaction (``authorize_write_locking``).
    """
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_MEDIA_WRITE
    )
    status = read_business_status(db, business_id)
    if status is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    if status == BusinessStatus.CLOSED.value:
        raise InvalidStateError("cannot modify the media of a closed business")


def authorize_write_locking(db: Session, actor: ActorContext, business_id: uuid.UUID) -> None:
    """Capability, Business ``FOR UPDATE`` lock, and lifecycle — the write
    preamble for the authoritative final transaction (mirrors the catalog
    preamble; the Business row is the deterministic first lock)."""
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_MEDIA_WRITE
    )
    status = lock_business_status(db, business_id)
    if status is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    if status == BusinessStatus.CLOSED.value:
        raise InvalidStateError("cannot modify the media of a closed business")


def authorize_write_locking_by_user_id(
    db: Session, user_id: uuid.UUID, business_id: uuid.UUID
) -> None:
    """The locking write preamble addressed by user id (upload worker).

    The async upload route may not pass an ORM object or session into the
    worker thread (final correction 2); the worker re-authorizes from the
    scalar actor user id in its OWN session. Same semantics as
    ``authorize_write_locking``: nonmember → 404, missing capability → 403,
    closed → 409, and the Business row is locked ``FOR UPDATE``.
    """
    role = memberships.get_role(db, business_id=business_id, user_id=user_id)
    if role is None:
        raise ResourceNotFoundError("Business not found.")
    if not role_has_capability(role, Capability.BUSINESS_MEDIA_WRITE):
        raise PermissionDeniedError()
    status = lock_business_status(db, business_id)
    if status is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    if status == BusinessStatus.CLOSED.value:
        raise InvalidStateError("cannot modify the media of a closed business")
