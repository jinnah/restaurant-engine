"""Business application service (M2B).

Owns the business lifecycle transactions (blueprint §14.1). Authorization
is enforced here, in the service, not only in an HTTP dependency (approved
decision 4): platform operations call ``identity.policies`` for the platform
capability; the member read calls ``identity.authorization`` for the
membership capability. A non-HTTP caller is enforced identically.

Cross-domain coordination: activation reads the owner count from the
identity memberships read model inside the same locked transaction — one
transaction spanning ``businesses`` and ``memberships``, owned by this
service, never by importing identity's ORM model.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidStateError, ResourceNotFoundError
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import BusinessCreatedDetails, BusinessStatusChangedDetails
from app.domains.businesses import repository
from app.domains.businesses.lifecycle import BusinessStatus, can_transition
from app.domains.businesses.models import Business
from app.domains.businesses.schemas import BusinessCreate, BusinessPage, BusinessSummary
from app.domains.identity import memberships
from app.domains.identity.actor import ActorContext
from app.domains.identity.policies import Capability, require_platform_capability

_MANAGE = Capability.PLATFORM_BUSINESSES_MANAGE


def _to_summary(business: Business) -> BusinessSummary:
    return BusinessSummary(
        id=business.id,
        name=business.name,
        slug=business.slug,
        status=business.status,
        timezone=business.timezone,
        currency=business.currency,
        created_at=business.created_at,
        updated_at=business.updated_at,
    )


def create_business(db: Session, actor: ActorContext, payload: BusinessCreate) -> BusinessSummary:
    """Create a business in ``provisioning`` (platform capability)."""
    require_platform_capability(actor, _MANAGE)
    business = Business(
        name=payload.name,
        slug=payload.slug,
        status=BusinessStatus.PROVISIONING.value,
        timezone=payload.timezone,
        currency=payload.currency,
    )
    repository.add(db, business)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        # Translate only the slug-uniqueness violation; any other integrity
        # failure is a real error and must propagate (approved point 8).
        if _is_slug_conflict(exc):
            raise ConflictError(f"slug '{payload.slug}' is already taken") from None
        raise
    recorder.record(
        db,
        AuditAction.BUSINESS_CREATED,
        actor_user_id=actor.user.id,
        business_id=business.id,
        target_type="business",
        target_id=str(business.id),
        details=BusinessCreatedDetails(slug=business.slug),
    )
    db.commit()
    return _to_summary(business)


def list_businesses(db: Session, actor: ActorContext, *, limit: int, offset: int) -> BusinessPage:
    """Bounded, deterministically ordered platform catalog page."""
    require_platform_capability(actor, _MANAGE)
    items, total = repository.list_page(db, limit=limit, offset=offset)
    return BusinessPage(
        items=[_to_summary(b) for b in items], total=total, limit=limit, offset=offset
    )


def get_business_platform(
    db: Session, actor: ActorContext, business_id: uuid.UUID
) -> BusinessSummary:
    """Platform read of any business (existence is visible to platform)."""
    require_platform_capability(actor, _MANAGE)
    business = repository.get(db, business_id)
    if business is None:
        raise ResourceNotFoundError("Business not found.")
    return _to_summary(business)


def get_business_for_member(
    db: Session, actor: ActorContext, business_id: uuid.UUID
) -> BusinessSummary:
    """Member read of their own business.

    Returns 200 even when the tenant is suspended, so the member can see the
    status (approved ruling 2). Nonmembers — including platform admins with
    no membership — get 404 (existence non-disclosure).
    """
    from app.domains.identity.authorization import require_membership_capability

    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_VIEW
    )
    business = repository.get(db, business_id)
    if business is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    return _to_summary(business)


def activate(db: Session, actor: ActorContext, business_id: uuid.UUID) -> BusinessSummary:
    """provisioning → active. Requires at least one owner (decision 6)."""
    return _transition(
        db,
        actor,
        business_id,
        expected=BusinessStatus.PROVISIONING,
        target=BusinessStatus.ACTIVE,
        action=AuditAction.BUSINESS_ACTIVATED,
    )


def suspend(db: Session, actor: ActorContext, business_id: uuid.UUID) -> BusinessSummary:
    """active → suspended."""
    return _transition(
        db,
        actor,
        business_id,
        expected=BusinessStatus.ACTIVE,
        target=BusinessStatus.SUSPENDED,
        action=AuditAction.BUSINESS_SUSPENDED,
    )


def reactivate(db: Session, actor: ActorContext, business_id: uuid.UUID) -> BusinessSummary:
    """suspended → active (retains its owners)."""
    return _transition(
        db,
        actor,
        business_id,
        expected=BusinessStatus.SUSPENDED,
        target=BusinessStatus.ACTIVE,
        action=AuditAction.BUSINESS_REACTIVATED,
    )


def close(db: Session, actor: ActorContext, business_id: uuid.UUID) -> BusinessSummary:
    """suspended → closed. Terminal; memberships are retained (decision 6)."""
    return _transition(
        db,
        actor,
        business_id,
        expected=BusinessStatus.SUSPENDED,
        target=BusinessStatus.CLOSED,
        action=AuditAction.BUSINESS_CLOSED,
    )


def _transition(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    *,
    expected: BusinessStatus,
    target: BusinessStatus,
    action: AuditAction,
) -> BusinessSummary:
    # Each endpoint declares exactly one legal source state, so the endpoint
    # (not just the shared table) fixes which transition it performs — a
    # command can never reach a target through the wrong source (e.g.
    # reactivate must not activate a provisioning tenant, bypassing the
    # owner guard).
    assert can_transition(expected, target)  # noqa: S101 - endpoint wiring invariant
    require_platform_capability(actor, _MANAGE)
    # FOR UPDATE serializes concurrent transitions on this business.
    business = repository.get_for_update(db, business_id)
    if business is None:
        raise ResourceNotFoundError("Business not found.")
    current = BusinessStatus(business.status)
    if current is not expected:
        raise InvalidStateError(f"cannot {action.value.split('.')[1]} a {current.value} business")
    # Entering active always requires at least one owner (decision 6): the
    # guard covers activate and reactivate, so there is no zero-owner path
    # into active regardless of which command is used.
    if (
        target is BusinessStatus.ACTIVE
        and memberships.count_owners(db, business_id=business_id) == 0
    ):
        raise InvalidStateError("cannot activate a business without an owner")

    business.status = target.value
    # Explicitly bump updated_at on the DB clock (approved amendment 4), in
    # addition to the model's onupdate, so the change is unmistakable and
    # comparable to created_at under one clock source.
    business.updated_at = func.now()
    recorder.record(
        db,
        action,
        actor_user_id=actor.user.id,
        business_id=business.id,
        target_type="business",
        target_id=str(business.id),
        details=BusinessStatusChangedDetails(
            previous_status=current.value, new_status=target.value
        ),
    )
    db.commit()
    db.refresh(business)
    return _to_summary(business)


def _is_slug_conflict(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == "uq_businesses_slug"
