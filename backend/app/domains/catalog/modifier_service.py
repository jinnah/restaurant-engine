"""Modifier application service (M3B, ADR-017).

The modifier workflows of the catalog domain: groups and options, their
selection rules, ordering, availability, and computed satisfiability.
Shares the M3A authorization preamble, business-row lock, and
transaction-boundary error conversion through ``service_support`` — one
implementation, no drift (D10 service-file ruling).

Satisfiability (D5) is computed from the authoritative post-mutation
state and returned on every group representation; it is never stored and
never blocks a write. Positions stay dense 0..n-1 per scope; full-set
reorders are exact-set-validated, atomic, and no-op-suppressed (an
identical permutation writes nothing and audits nothing).
"""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import (
    ApiError,
    ConflictError,
    ErrorCode,
    ResourceNotFoundError,
)
from app.domains.catalog import policies, repository
from app.domains.catalog.models import ModifierGroup, ModifierOption
from app.domains.catalog.schemas import (
    ModifierGroupCreate,
    ModifierGroupReorder,
    ModifierGroupsView,
    ModifierGroupUpdate,
    ModifierGroupView,
    ModifierOptionCreate,
    ModifierOptionReorder,
    ModifierOptionUpdate,
    ModifierOptionView,
)
from app.domains.catalog.service_support import (
    authorize_read,
    authorize_write,
    safe_commit,
    safe_flush,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.policies import Capability


def _limit_conflict(message: str, limit: int) -> ApiError:
    return ApiError(409, ErrorCode.CONFLICT, message, details={"limit": limit})


def _option_view(option: ModifierOption) -> ModifierOptionView:
    return ModifierOptionView(
        id=option.id,
        group_id=option.group_id,
        name=option.name,
        price_delta_minor=option.price_delta_minor,
        is_available=option.is_available,
        position=option.position,
        created_at=option.created_at,
        updated_at=option.updated_at,
    )


def _group_view(group: ModifierGroup, options: list[ModifierOption]) -> ModifierGroupView:
    active_count = sum(1 for option in options if option.is_available)
    return ModifierGroupView(
        id=group.id,
        item_id=group.item_id,
        name=group.name,
        min_select=group.min_select,
        max_select=group.max_select,
        position=group.position,
        active_option_count=active_count,
        is_satisfiable=policies.is_group_satisfiable(
            group.min_select, group.max_select, active_count
        ),
        options=[_option_view(option) for option in options],
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def _load_group_view(
    db: Session, business_id: uuid.UUID, group: ModifierGroup
) -> ModifierGroupView:
    options = repository.list_options_for_group(db, business_id=business_id, group_id=group.id)
    return _group_view(group, options)


def _groups_view(db: Session, business_id: uuid.UUID, item_id: uuid.UUID) -> ModifierGroupsView:
    groups = repository.list_groups_for_item(db, business_id=business_id, item_id=item_id)
    options_by_group = repository.list_options_for_groups(
        db, business_id=business_id, group_ids=[group.id for group in groups]
    )
    return ModifierGroupsView(
        item_id=item_id,
        groups=[_group_view(group, options_by_group.get(group.id, [])) for group in groups],
    )


def _require_item(db: Session, business_id: uuid.UUID, item_id: uuid.UUID) -> None:
    if repository.get_item(db, business_id=business_id, item_id=item_id) is None:
        raise ResourceNotFoundError("Item not found.")


def _require_group(db: Session, business_id: uuid.UUID, group_id: uuid.UUID) -> ModifierGroup:
    group = repository.get_group(db, business_id=business_id, group_id=group_id)
    if group is None:
        raise ResourceNotFoundError("Modifier group not found.")
    return group


def _require_option(db: Session, business_id: uuid.UUID, option_id: uuid.UUID) -> ModifierOption:
    option = repository.get_option(db, business_id=business_id, option_id=option_id)
    if option is None:
        raise ResourceNotFoundError("Option not found.")
    return option


# --- Read ---------------------------------------------------------------------


def get_modifier_groups(
    db: Session, actor: ActorContext, business_id: uuid.UUID, item_id: uuid.UUID
) -> ModifierGroupsView:
    """The bounded per-item modifier tree (D2), any member."""
    authorize_read(db, actor, business_id)
    _require_item(db, business_id, item_id)
    return _groups_view(db, business_id, item_id)


# --- Group commands -----------------------------------------------------------


def create_group(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ModifierGroupCreate,
) -> ModifierGroupView:
    """Create a group, appended at the end of the item's groups.

    Zero options is a valid, unsatisfiable construction state (D5).
    """
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    _require_item(db, business_id, item_id)
    if (
        repository.count_groups_for_business(db, business_id=business_id)
        >= policies.MAX_MODIFIER_GROUPS_PER_BUSINESS
    ):
        raise _limit_conflict(
            "Modifier group limit reached for this business.",
            policies.MAX_MODIFIER_GROUPS_PER_BUSINESS,
        )
    item_count = repository.count_groups_for_item(db, business_id=business_id, item_id=item_id)
    if item_count >= policies.MAX_MODIFIER_GROUPS_PER_ITEM:
        raise _limit_conflict(
            "Modifier group limit reached for this item.",
            policies.MAX_MODIFIER_GROUPS_PER_ITEM,
        )
    if repository.group_name_exists(
        db, business_id=business_id, item_id=item_id, name=payload.name
    ):
        raise ConflictError("a modifier group with this name already exists on this item")
    group = ModifierGroup(
        business_id=business_id,
        item_id=item_id,
        name=payload.name,
        min_select=payload.min_select,
        max_select=payload.max_select,
        position=item_count,
    )
    repository.add(db, group)
    safe_flush(db)
    safe_commit(db)
    return _group_view(group, [])


def update_group(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ModifierGroupUpdate,
) -> ModifierGroupView:
    """Partial group update; the effective min/max pair is validated
    against stored values when only one side is supplied."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    group = _require_group(db, business_id, group_id)
    provided = payload.model_fields_set

    new_min = (
        payload.min_select
        if ("min_select" in provided and payload.min_select is not None)
        else group.min_select
    )
    new_max = payload.max_select if "max_select" in provided else group.max_select
    if new_max is not None and new_min > new_max:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "min_select cannot exceed max_select",
        )

    changed: list[str] = []
    if "name" in provided and payload.name is not None and payload.name != group.name:
        if repository.group_name_exists(
            db,
            business_id=business_id,
            item_id=group.item_id,
            name=payload.name,
            exclude_id=group.id,
        ):
            raise ConflictError("a modifier group with this name already exists on this item")
        group.name = payload.name
        changed.append("name")
    if new_min != group.min_select:
        group.min_select = new_min
        changed.append("min_select")
    if "max_select" in provided and new_max != group.max_select:
        group.max_select = new_max
        changed.append("max_select")
    if changed:
        group.updated_at = func.now()
        safe_flush(db)
    safe_commit(db)
    db.refresh(group)
    return _load_group_view(db, business_id, group)


def delete_group(
    db: Session, actor: ActorContext, business_id: uuid.UUID, group_id: uuid.UUID
) -> None:
    """Delete a group; its options CASCADE; sibling positions compact."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    group = _require_group(db, business_id, group_id)
    item_id = group.item_id
    position = group.position
    repository.delete_group(db, group)
    safe_flush(db)
    repository.close_group_position_gap(
        db, business_id=business_id, item_id=item_id, position=position
    )
    safe_commit(db)


def reorder_groups(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ModifierGroupReorder,
) -> ModifierGroupsView:
    """Full-set, atomic, normalizing group reorder (no-op suppressed)."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    _require_item(db, business_id, item_id)
    current_ids = repository.list_group_ids_for_item(db, business_id=business_id, item_id=item_id)
    if sorted(payload.ordered_group_ids, key=str) != sorted(current_ids, key=str):
        raise ConflictError(
            "the supplied ids do not exactly match the item's modifier groups; refresh and retry"
        )
    if payload.ordered_group_ids == current_ids:
        # Identical permutation: no writes, no audit (ADR-017 no-op rule).
        safe_commit(db)
        return _groups_view(db, business_id, item_id)
    repository.set_group_positions(
        db, business_id=business_id, item_id=item_id, ordered_ids=payload.ordered_group_ids
    )
    safe_commit(db)
    return _groups_view(db, business_id, item_id)


# --- Option commands ----------------------------------------------------------


def create_option(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ModifierOptionCreate,
) -> ModifierGroupView:
    """Create an option (appended, available); returns the parent group."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    group = _require_group(db, business_id, group_id)
    if (
        repository.count_options_for_business(db, business_id=business_id)
        >= policies.MAX_MODIFIER_OPTIONS_PER_BUSINESS
    ):
        raise _limit_conflict(
            "Option limit reached for this business.",
            policies.MAX_MODIFIER_OPTIONS_PER_BUSINESS,
        )
    group_count = repository.count_options_for_group(db, business_id=business_id, group_id=group_id)
    if group_count >= policies.MAX_MODIFIER_OPTIONS_PER_GROUP:
        raise _limit_conflict(
            "Option limit reached for this group.",
            policies.MAX_MODIFIER_OPTIONS_PER_GROUP,
        )
    if repository.option_name_exists(
        db, business_id=business_id, group_id=group_id, name=payload.name
    ):
        raise ConflictError("an option with this name already exists in this group")
    option = ModifierOption(
        business_id=business_id,
        group_id=group_id,
        name=payload.name,
        price_delta_minor=payload.price_delta_minor,
        position=group_count,
    )
    repository.add(db, option)
    safe_flush(db)
    safe_commit(db)
    return _load_group_view(db, business_id, group)


def update_option(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: ModifierOptionUpdate,
) -> ModifierGroupView:
    """Partial option update (availability rides this PATCH, D3);
    returns the recomputed parent group."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    option = _require_option(db, business_id, option_id)
    group = _require_group(db, business_id, option.group_id)
    provided = payload.model_fields_set

    changed: list[str] = []
    if "name" in provided and payload.name is not None and payload.name != option.name:
        if repository.option_name_exists(
            db,
            business_id=business_id,
            group_id=option.group_id,
            name=payload.name,
            exclude_id=option.id,
        ):
            raise ConflictError("an option with this name already exists in this group")
        option.name = payload.name
        changed.append("name")
    if (
        "price_delta_minor" in provided
        and payload.price_delta_minor is not None
        and payload.price_delta_minor != option.price_delta_minor
    ):
        option.price_delta_minor = payload.price_delta_minor
        changed.append("price_delta_minor")
    if (
        "is_available" in provided
        and payload.is_available is not None
        and payload.is_available != option.is_available
    ):
        option.is_available = payload.is_available
        changed.append("is_available")
    if changed:
        option.updated_at = func.now()
        safe_flush(db)
    safe_commit(db)
    db.refresh(option)
    return _load_group_view(db, business_id, group)


def delete_option(
    db: Session, actor: ActorContext, business_id: uuid.UUID, option_id: uuid.UUID
) -> ModifierGroupView:
    """Delete an option; sibling positions compact; returns the surviving
    parent group (possibly with zero active options, unsatisfiable)."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    option = _require_option(db, business_id, option_id)
    group = _require_group(db, business_id, option.group_id)
    group_id = option.group_id
    position = option.position
    repository.delete_option(db, option)
    safe_flush(db)
    repository.close_option_position_gap(
        db, business_id=business_id, group_id=group_id, position=position
    )
    safe_commit(db)
    return _load_group_view(db, business_id, group)


def reorder_options(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ModifierOptionReorder,
) -> ModifierGroupView:
    """Full-set, atomic, normalizing option reorder (no-op suppressed)."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    group = _require_group(db, business_id, group_id)
    current_ids = repository.list_option_ids_for_group(
        db, business_id=business_id, group_id=group_id
    )
    if sorted(payload.ordered_option_ids, key=str) != sorted(current_ids, key=str):
        raise ConflictError(
            "the supplied ids do not exactly match the group's options; refresh and retry"
        )
    if payload.ordered_option_ids == current_ids:
        safe_commit(db)
        return _load_group_view(db, business_id, group)
    repository.set_option_positions(
        db, business_id=business_id, group_id=group_id, ordered_ids=payload.ordered_option_ids
    )
    safe_commit(db)
    return _load_group_view(db, business_id, group)
