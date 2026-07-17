"""Tenant application service (M2B).

Owns the restaurant lifecycle transactions (blueprint §14.1). Authorization
is enforced here, in the service, not only in an HTTP dependency (approved
decision 4): platform operations call ``identity.policies`` for the platform
capability; the member read calls ``identity.authorization`` for the
membership capability. A non-HTTP caller is enforced identically.

Cross-domain coordination: activation reads the owner count from the
identity memberships read model inside the same locked transaction — one
business transaction spanning ``restaurants`` and ``memberships``, owned by
this service, never by importing identity's ORM model.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidStateError, ResourceNotFoundError
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import TenantCreatedDetails, TenantStatusChangedDetails
from app.domains.identity import memberships
from app.domains.identity.actor import ActorContext
from app.domains.identity.policies import Capability, require_platform_capability
from app.domains.tenants import repository
from app.domains.tenants.lifecycle import RestaurantStatus, can_transition
from app.domains.tenants.models import Restaurant
from app.domains.tenants.schemas import RestaurantCreate, RestaurantPage, RestaurantSummary

_MANAGE = Capability.PLATFORM_RESTAURANTS_MANAGE


def _to_summary(restaurant: Restaurant) -> RestaurantSummary:
    return RestaurantSummary(
        id=restaurant.id,
        name=restaurant.name,
        slug=restaurant.slug,
        status=restaurant.status,
        timezone=restaurant.timezone,
        currency=restaurant.currency,
        created_at=restaurant.created_at,
        updated_at=restaurant.updated_at,
    )


def create_restaurant(
    db: Session, actor: ActorContext, payload: RestaurantCreate
) -> RestaurantSummary:
    """Create a restaurant in ``provisioning`` (platform capability)."""
    require_platform_capability(actor, _MANAGE)
    restaurant = Restaurant(
        name=payload.name,
        slug=payload.slug,
        status=RestaurantStatus.PROVISIONING.value,
        timezone=payload.timezone,
        currency=payload.currency,
    )
    repository.add(db, restaurant)
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
        AuditAction.TENANT_CREATED,
        actor_user_id=actor.user.id,
        restaurant_id=restaurant.id,
        target_type="restaurant",
        target_id=str(restaurant.id),
        details=TenantCreatedDetails(slug=restaurant.slug),
    )
    db.commit()
    return _to_summary(restaurant)


def list_restaurants(
    db: Session, actor: ActorContext, *, limit: int, offset: int
) -> RestaurantPage:
    """Bounded, deterministically ordered platform catalog page."""
    require_platform_capability(actor, _MANAGE)
    items, total = repository.list_page(db, limit=limit, offset=offset)
    return RestaurantPage(
        items=[_to_summary(r) for r in items], total=total, limit=limit, offset=offset
    )


def get_restaurant_platform(
    db: Session, actor: ActorContext, restaurant_id: uuid.UUID
) -> RestaurantSummary:
    """Platform read of any restaurant (existence is visible to platform)."""
    require_platform_capability(actor, _MANAGE)
    restaurant = repository.get(db, restaurant_id)
    if restaurant is None:
        raise ResourceNotFoundError("Restaurant not found.")
    return _to_summary(restaurant)


def get_restaurant_for_member(
    db: Session, actor: ActorContext, restaurant_id: uuid.UUID
) -> RestaurantSummary:
    """Member read of their own restaurant.

    Returns 200 even when the tenant is suspended, so the member can see the
    status (approved ruling 2). Nonmembers — including platform admins with
    no membership — get 404 (existence non-disclosure).
    """
    from app.domains.identity.authorization import require_membership_capability

    require_membership_capability(
        db, actor, restaurant_id=restaurant_id, capability=Capability.RESTAURANT_VIEW
    )
    restaurant = repository.get(db, restaurant_id)
    if restaurant is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Restaurant not found.")
    return _to_summary(restaurant)


def activate(db: Session, actor: ActorContext, restaurant_id: uuid.UUID) -> RestaurantSummary:
    """provisioning → active. Requires at least one owner (decision 6)."""
    return _transition(
        db,
        actor,
        restaurant_id,
        expected=RestaurantStatus.PROVISIONING,
        target=RestaurantStatus.ACTIVE,
        action=AuditAction.TENANT_ACTIVATED,
    )


def suspend(db: Session, actor: ActorContext, restaurant_id: uuid.UUID) -> RestaurantSummary:
    """active → suspended."""
    return _transition(
        db,
        actor,
        restaurant_id,
        expected=RestaurantStatus.ACTIVE,
        target=RestaurantStatus.SUSPENDED,
        action=AuditAction.TENANT_SUSPENDED,
    )


def reactivate(db: Session, actor: ActorContext, restaurant_id: uuid.UUID) -> RestaurantSummary:
    """suspended → active (retains its owners)."""
    return _transition(
        db,
        actor,
        restaurant_id,
        expected=RestaurantStatus.SUSPENDED,
        target=RestaurantStatus.ACTIVE,
        action=AuditAction.TENANT_REACTIVATED,
    )


def close(db: Session, actor: ActorContext, restaurant_id: uuid.UUID) -> RestaurantSummary:
    """suspended → closed. Terminal; memberships are retained (decision 6)."""
    return _transition(
        db,
        actor,
        restaurant_id,
        expected=RestaurantStatus.SUSPENDED,
        target=RestaurantStatus.CLOSED,
        action=AuditAction.TENANT_CLOSED,
    )


def _transition(
    db: Session,
    actor: ActorContext,
    restaurant_id: uuid.UUID,
    *,
    expected: RestaurantStatus,
    target: RestaurantStatus,
    action: AuditAction,
) -> RestaurantSummary:
    # Each endpoint declares exactly one legal source state, so the endpoint
    # (not just the shared table) fixes which transition it performs — a
    # command can never reach a target through the wrong source (e.g.
    # reactivate must not activate a provisioning tenant, bypassing the
    # owner guard).
    assert can_transition(expected, target)  # noqa: S101 - endpoint wiring invariant
    require_platform_capability(actor, _MANAGE)
    # FOR UPDATE serializes concurrent transitions on this restaurant.
    restaurant = repository.get_for_update(db, restaurant_id)
    if restaurant is None:
        raise ResourceNotFoundError("Restaurant not found.")
    current = RestaurantStatus(restaurant.status)
    if current is not expected:
        raise InvalidStateError(f"cannot {action.value.split('.')[1]} a {current.value} restaurant")
    # Entering active always requires at least one owner (decision 6): the
    # guard covers activate and reactivate, so there is no zero-owner path
    # into active regardless of which command is used.
    if (
        target is RestaurantStatus.ACTIVE
        and memberships.count_owners(db, restaurant_id=restaurant_id) == 0
    ):
        raise InvalidStateError("cannot activate a restaurant without an owner")

    restaurant.status = target.value
    # Explicitly bump updated_at on the DB clock (approved amendment 4), in
    # addition to the model's onupdate, so the change is unmistakable and
    # comparable to created_at under one clock source.
    restaurant.updated_at = func.now()
    recorder.record(
        db,
        action,
        actor_user_id=actor.user.id,
        restaurant_id=restaurant.id,
        target_type="restaurant",
        target_id=str(restaurant.id),
        details=TenantStatusChangedDetails(previous_status=current.value, new_status=target.value),
    )
    db.commit()
    db.refresh(restaurant)
    return _to_summary(restaurant)


def _is_slug_conflict(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == "uq_restaurants_slug"
