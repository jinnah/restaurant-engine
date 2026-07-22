"""Catalog application service (M3A, ADR-017).

Owns every catalog transaction. Authorization is enforced here, in the
service (M2B discipline): reads require ``business.view``; general writes
require ``business.catalog.write``; the availability command requires
``business.catalog.availability`` (staff-reachable, ruling D4).

Every mutation follows one preamble: membership capability check (404/403
semantics), then ``SELECT … FOR UPDATE`` on the Business row — the
deterministic first lock (ADR-014/ADR-017) that serializes per-tenant
catalog writes, makes count-limit checks race-safe, and pins the
lifecycle status (closed businesses are immutable, D8). Positions stay
dense 0..n-1 per scope: creation appends, deletion closes the gap,
reorder rewrites the full permutation under the DEFERRED unique.

Concurrency contract (D5): row locks serialize writes but do not detect
stale editors — concurrent valid edits are last-committed-write unless a
structural invariant (uniqueness, limits, exact-set reorder) turns the
loser into a 409.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import (
    ApiError,
    ConflictError,
    ErrorCode,
    ResourceNotFoundError,
)
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import (
    CatalogCategoryDetails,
    CatalogCategoryUpdatedDetails,
    CatalogItemAvailabilityDetails,
    CatalogItemCreatedDetails,
    CatalogItemDeletedDetails,
    CatalogItemImageChangedDetails,
    CatalogItemUpdatedDetails,
    CatalogReorderDetails,
)
from app.domains.catalog import dietary, policies, repository
from app.domains.catalog.models import MenuCategory, MenuItem, MenuItemDietaryTag
from app.domains.catalog.schemas import (
    AdminMenu,
    CategoryCreate,
    CategoryReorder,
    CategorySummary,
    CategoryUpdate,
    CategoryWithItems,
    ItemAvailabilitySet,
    ItemCreate,
    ItemImageSet,
    ItemReorder,
    ItemSummary,
    ItemUpdate,
)
from app.domains.catalog.service_support import (
    authorize_read,
    authorize_write,
    safe_commit,
    safe_flush,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.policies import Capability
from app.domains.media import service as media_service


def _category_summary(category: MenuCategory) -> CategorySummary:
    return CategorySummary(
        id=category.id,
        name=category.name,
        description=category.description,
        position=category.position,
        is_visible=category.is_visible,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _item_summary(item: MenuItem, tags: Sequence[str]) -> ItemSummary:
    # Reads are fail-closed on dietary tags (D6): unregistered stored
    # values are never surfaced.
    return ItemSummary(
        id=item.id,
        category_id=item.category_id,
        name=item.name,
        description=item.description,
        price_minor=item.price_minor,
        position=item.position,
        is_available=item.is_available,
        is_hidden=item.is_hidden,
        is_featured=item.is_featured,
        dietary_tags=dietary.filter_known(tags),
        image_media_id=item.image_media_id,
        image_alt_text=item.image_alt_text,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


# --- Reads -------------------------------------------------------------------


def get_admin_menu(db: Session, actor: ActorContext, business_id: uuid.UUID) -> AdminMenu:
    """The complete administrative menu tree (hidden entries included)."""
    authorize_read(db, actor, business_id)
    categories = repository.list_categories(db, business_id=business_id)
    items = repository.list_items(db, business_id=business_id)
    tags_by_item = repository.list_tags_for_business(db, business_id=business_id)
    items_by_category: dict[uuid.UUID, list[ItemSummary]] = {}
    for item in items:
        items_by_category.setdefault(item.category_id, []).append(
            _item_summary(item, tags_by_item.get(item.id, []))
        )
    return AdminMenu(
        categories=[
            CategoryWithItems(
                **_category_summary(category).model_dump(),
                items=items_by_category.get(category.id, []),
            )
            for category in categories
        ]
    )


def get_item(
    db: Session, actor: ActorContext, business_id: uuid.UUID, item_id: uuid.UUID
) -> ItemSummary:
    authorize_read(db, actor, business_id)
    item = repository.get_item(db, business_id=business_id, item_id=item_id)
    if item is None:
        raise ResourceNotFoundError("Item not found.")
    tags = repository.list_tags_for_item(db, business_id=business_id, item_id=item_id)
    return _item_summary(item, tags)


# --- Category commands -------------------------------------------------------


def create_category(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: CategoryCreate
) -> CategorySummary:
    """Create a category, appended at the end of the menu."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    count = repository.count_categories(db, business_id=business_id)
    if count >= policies.MAX_CATEGORIES_PER_BUSINESS:
        raise ApiError(
            409,
            ErrorCode.CONFLICT,
            "Category limit reached.",
            details={"limit": policies.MAX_CATEGORIES_PER_BUSINESS},
        )
    if repository.category_name_exists(db, business_id=business_id, name=payload.name):
        raise ConflictError("a category with this name already exists")
    category = MenuCategory(
        business_id=business_id,
        name=payload.name,
        description=payload.description,
        position=count,
    )
    repository.add(db, category)
    safe_flush(db)
    recorder.record(
        db,
        AuditAction.CATALOG_CATEGORY_CREATED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="menu_category",
        target_id=str(category.id),
        details=CatalogCategoryDetails(name=category.name),
    )
    safe_commit(db)
    return _category_summary(category)


def update_category(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: CategoryUpdate,
) -> CategorySummary:
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    category = repository.get_category(db, business_id=business_id, category_id=category_id)
    if category is None:
        raise ResourceNotFoundError("Category not found.")
    provided = payload.model_fields_set
    changed: list[str] = []
    if "name" in provided and payload.name is not None and payload.name != category.name:
        if repository.category_name_exists(
            db, business_id=business_id, name=payload.name, exclude_id=category.id
        ):
            raise ConflictError("a category with this name already exists")
        category.name = payload.name
        changed.append("name")
    if "description" in provided and payload.description != category.description:
        category.description = payload.description
        changed.append("description")
    if (
        "is_visible" in provided
        and payload.is_visible is not None
        and payload.is_visible != category.is_visible
    ):
        category.is_visible = payload.is_visible
        changed.append("is_visible")
    if changed:
        category.updated_at = func.now()
        safe_flush(db)
        recorder.record(
            db,
            AuditAction.CATALOG_CATEGORY_UPDATED,
            actor_user_id=actor.user.id,
            business_id=business_id,
            target_type="menu_category",
            target_id=str(category.id),
            details=CatalogCategoryUpdatedDetails(
                name=category.name, changed_fields=",".join(sorted(changed))
            ),
        )
    safe_commit(db)
    db.refresh(category)
    return _category_summary(category)


def delete_category(
    db: Session, actor: ActorContext, business_id: uuid.UUID, category_id: uuid.UUID
) -> None:
    """Delete an empty category and close its position gap (D7)."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    category = repository.get_category(db, business_id=business_id, category_id=category_id)
    if category is None:
        raise ResourceNotFoundError("Category not found.")
    if repository.count_items_in_category(db, business_id=business_id, category_id=category_id):
        raise ConflictError("the category is not empty; move or delete its items first")
    position = category.position
    name = category.name
    deleted_id = category.id
    repository.delete_category(db, category)
    safe_flush(db)
    repository.close_category_position_gap(db, business_id=business_id, position=position)
    recorder.record(
        db,
        AuditAction.CATALOG_CATEGORY_DELETED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="menu_category",
        target_id=str(deleted_id),
        details=CatalogCategoryDetails(name=name),
    )
    safe_commit(db)


def reorder_categories(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: CategoryReorder
) -> AdminMenu:
    """Full-set, atomic, normalizing category reorder (naturally idempotent)."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    categories = repository.list_categories(db, business_id=business_id)
    current_ids = [category.id for category in categories]
    if sorted(payload.ordered_category_ids, key=str) != sorted(current_ids, key=str):
        raise ConflictError(
            "the supplied ids do not exactly match the business's categories; refresh and retry"
        )
    if payload.ordered_category_ids == current_ids:
        # R-1 (ADR-017): an identical full-set permutation is a no-op —
        # authoritative state, no position writes, no audit event.
        safe_commit(db)
        return get_admin_menu(db, actor, business_id)
    repository.set_category_positions(
        db, business_id=business_id, ordered_ids=payload.ordered_category_ids
    )
    recorder.record(
        db,
        AuditAction.CATALOG_CATEGORIES_REORDERED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="business",
        target_id=str(business_id),
        details=CatalogReorderDetails(count=len(payload.ordered_category_ids)),
    )
    safe_commit(db)
    return get_admin_menu(db, actor, business_id)


# --- Item commands -----------------------------------------------------------


def create_item(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: ItemCreate,
) -> ItemSummary:
    """Create an item, appended at the end of its category."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    category = repository.get_category(db, business_id=business_id, category_id=category_id)
    if category is None:
        raise ResourceNotFoundError("Category not found.")
    if repository.count_items(db, business_id=business_id) >= policies.MAX_ITEMS_PER_BUSINESS:
        raise ApiError(
            409,
            ErrorCode.CONFLICT,
            "Item limit reached for this business.",
            details={"limit": policies.MAX_ITEMS_PER_BUSINESS},
        )
    category_count = repository.count_items_in_category(
        db, business_id=business_id, category_id=category_id
    )
    if category_count >= policies.MAX_ITEMS_PER_CATEGORY:
        raise ApiError(
            409,
            ErrorCode.CONFLICT,
            "Item limit reached for this category.",
            details={"limit": policies.MAX_ITEMS_PER_CATEGORY},
        )
    if repository.item_name_exists(
        db, business_id=business_id, category_id=category_id, name=payload.name
    ):
        raise ConflictError("an item with this name already exists in this category")
    item = MenuItem(
        business_id=business_id,
        category_id=category_id,
        name=payload.name,
        description=payload.description,
        price_minor=payload.price_minor,
        position=category_count,
    )
    repository.add(db, item)
    safe_flush(db)
    for tag in payload.dietary_tags:
        repository.add(db, MenuItemDietaryTag(business_id=business_id, item_id=item.id, tag=tag))
    safe_flush(db)
    recorder.record(
        db,
        AuditAction.CATALOG_ITEM_CREATED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="menu_item",
        target_id=str(item.id),
        details=CatalogItemCreatedDetails(
            name=item.name, category_id=str(category_id), price_minor=item.price_minor
        ),
    )
    safe_commit(db)
    # Canonical tag order (review F4): the create response sorts exactly as
    # every subsequent read does — never request order.
    return _item_summary(item, sorted(payload.dietary_tags))


def update_item(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ItemUpdate,
) -> ItemSummary:
    """Partial item update, including category movement and featuring."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    item = repository.get_item(db, business_id=business_id, item_id=item_id)
    if item is None:
        raise ResourceNotFoundError("Item not found.")
    provided = payload.model_fields_set

    moving = (
        "category_id" in provided
        and payload.category_id is not None
        and payload.category_id != item.category_id
    )
    target_category_id = payload.category_id if moving and payload.category_id else item.category_id
    new_name = payload.name if ("name" in provided and payload.name is not None) else item.name

    # All validation reads run before any mutation so autoflush cannot
    # interleave half-applied state into the count/uniqueness queries.
    if moving:
        destination = repository.get_category(
            db, business_id=business_id, category_id=target_category_id
        )
        if destination is None:
            raise ResourceNotFoundError("Category not found.")
        if (
            repository.count_items_in_category(
                db, business_id=business_id, category_id=target_category_id
            )
            >= policies.MAX_ITEMS_PER_CATEGORY
        ):
            raise ApiError(
                409,
                ErrorCode.CONFLICT,
                "Item limit reached for this category.",
                details={"limit": policies.MAX_ITEMS_PER_CATEGORY},
            )
    name_changed = new_name != item.name
    if (name_changed or moving) and repository.item_name_exists(
        db,
        business_id=business_id,
        category_id=target_category_id,
        name=new_name,
        exclude_id=item.id,
    ):
        raise ConflictError("an item with this name already exists in this category")
    featuring = "is_featured" in provided and payload.is_featured is True and not item.is_featured
    if featuring and (
        repository.count_featured_items(db, business_id=business_id) >= policies.MAX_FEATURED_ITEMS
    ):
        raise ApiError(
            409,
            ErrorCode.CONFLICT,
            "Featured item limit reached.",
            details={"limit": policies.MAX_FEATURED_ITEMS},
        )
    destination_count = (
        repository.count_items_in_category(
            db, business_id=business_id, category_id=target_category_id
        )
        if moving
        else None
    )
    current_tags = (
        repository.list_tags_for_item(db, business_id=business_id, item_id=item.id)
        if "dietary_tags" in provided and payload.dietary_tags is not None
        else None
    )

    # Apply the mutation, tracking the closed-set change summary for audit.
    changed: list[str] = []
    price_minor_old: int | None = None
    price_minor_new: int | None = None
    old_category_id = item.category_id
    old_position = item.position
    if name_changed:
        item.name = new_name
        changed.append("name")
    if "description" in provided and payload.description != item.description:
        item.description = payload.description
        changed.append("description")
    if (
        "price_minor" in provided
        and payload.price_minor is not None
        and payload.price_minor != item.price_minor
    ):
        price_minor_old = item.price_minor
        price_minor_new = payload.price_minor
        item.price_minor = payload.price_minor
        changed.append("price_minor")
    if (
        "is_hidden" in provided
        and payload.is_hidden is not None
        and payload.is_hidden != item.is_hidden
    ):
        # Hiding never clears is_featured (R1): the flag is retained and
        # simply inert while hidden.
        item.is_hidden = payload.is_hidden
        changed.append("is_hidden")
    if (
        "is_featured" in provided
        and payload.is_featured is not None
        and payload.is_featured != item.is_featured
    ):
        item.is_featured = payload.is_featured
        changed.append("is_featured")
    if moving and destination_count is not None:
        item.category_id = target_category_id
        item.position = destination_count  # append at the destination's end
        changed.append("category_id")
    if (
        current_tags is not None
        and payload.dietary_tags is not None
        and sorted(payload.dietary_tags) != current_tags
    ):
        repository.replace_item_tags(
            db, business_id=business_id, item_id=item.id, tags=payload.dietary_tags
        )
        changed.append("dietary_tags")
    if changed:
        item.updated_at = func.now()
        safe_flush(db)
        if moving:
            # Close the source category's gap; the moved row no longer
            # matches its old (category, position) and is untouched by
            # the shift.
            repository.close_item_position_gap(
                db, business_id=business_id, category_id=old_category_id, position=old_position
            )
        recorder.record(
            db,
            AuditAction.CATALOG_ITEM_UPDATED,
            actor_user_id=actor.user.id,
            business_id=business_id,
            target_type="menu_item",
            target_id=str(item.id),
            details=CatalogItemUpdatedDetails(
                changed_fields=",".join(sorted(changed)),
                price_minor_old=price_minor_old,
                price_minor_new=price_minor_new,
                category_id=str(target_category_id) if moving else None,
            ),
        )
    safe_commit(db)
    db.refresh(item)
    tags = repository.list_tags_for_item(db, business_id=business_id, item_id=item.id)
    return _item_summary(item, tags)


def delete_item(
    db: Session, actor: ActorContext, business_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    """Delete an item; its dietary tags CASCADE; positions renormalize."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    item = repository.get_item(db, business_id=business_id, item_id=item_id)
    if item is None:
        raise ResourceNotFoundError("Item not found.")
    category_id = item.category_id
    position = item.position
    name = item.name
    deleted_id = item.id
    repository.delete_item(db, item)
    safe_flush(db)
    repository.close_item_position_gap(
        db, business_id=business_id, category_id=category_id, position=position
    )
    recorder.record(
        db,
        AuditAction.CATALOG_ITEM_DELETED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="menu_item",
        target_id=str(deleted_id),
        details=CatalogItemDeletedDetails(name=name, category_id=str(category_id)),
    )
    safe_commit(db)


def reorder_items(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: ItemReorder
) -> AdminMenu:
    """Full-set, atomic, normalizing item reorder within one category."""
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    category = repository.get_category(db, business_id=business_id, category_id=payload.category_id)
    if category is None:
        raise ResourceNotFoundError("Category not found.")
    current_ids = repository.list_item_ids_in_category(
        db, business_id=business_id, category_id=payload.category_id
    )
    if sorted(payload.ordered_item_ids, key=str) != sorted(current_ids, key=str):
        raise ConflictError(
            "the supplied ids do not exactly match the category's items; refresh and retry"
        )
    if payload.ordered_item_ids == current_ids:
        # R-1 (ADR-017): identical permutation — no writes, no audit.
        safe_commit(db)
        return get_admin_menu(db, actor, business_id)
    repository.set_item_positions(
        db,
        business_id=business_id,
        category_id=payload.category_id,
        ordered_ids=payload.ordered_item_ids,
    )
    recorder.record(
        db,
        AuditAction.CATALOG_ITEMS_REORDERED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="menu_category",
        target_id=str(payload.category_id),
        details=CatalogReorderDetails(count=len(payload.ordered_item_ids)),
    )
    safe_commit(db)
    return get_admin_menu(db, actor, business_id)


def set_item_availability(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ItemAvailabilitySet,
) -> ItemSummary:
    """The "sold out today" toggle — the one staff-reachable command (D4).

    Idempotent: setting the current value again succeeds without a state
    change. Availability is deliberately independent of ``is_hidden``
    (docs/03: separate states).
    """
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_AVAILABILITY)
    item = repository.get_item(db, business_id=business_id, item_id=item_id)
    if item is None:
        raise ResourceNotFoundError("Item not found.")
    if item.is_available != payload.is_available:
        item.is_available = payload.is_available
        item.updated_at = func.now()
        safe_flush(db)
        recorder.record(
            db,
            AuditAction.CATALOG_ITEM_AVAILABILITY_CHANGED,
            actor_user_id=actor.user.id,
            business_id=business_id,
            target_type="menu_item",
            target_id=str(item.id),
            details=CatalogItemAvailabilityDetails(
                availability="available" if payload.is_available else "sold_out"
            ),
        )
    safe_commit(db)
    db.refresh(item)
    tags = repository.list_tags_for_item(db, business_id=business_id, item_id=item_id)
    return _item_summary(item, tags)


def set_item_image(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ItemImageSet,
) -> ItemSummary:
    """Attach, replace, clear, or re-describe an item's image (M3C).

    One command covers four substantive changes and suppresses exact
    no-ops (final correction 3): a no-op returns the current item unchanged
    (no ``updated_at`` bump, no media promotion, no audit event). Attaching
    a media asset promotes it ``pending → active`` through the media domain
    (``claim_for_attachment``), inside this transaction which already holds
    the Business lock — the acyclic catalog → media dependency.
    """
    authorize_write(db, actor, business_id, Capability.BUSINESS_CATALOG_WRITE)
    item = repository.get_item(db, business_id=business_id, item_id=item_id)
    if item is None:
        raise ResourceNotFoundError("Item not found.")

    old_media = item.image_media_id
    old_alt = item.image_alt_text
    new_media = payload.media_id
    new_alt = payload.alt_text if new_media is not None else None

    media_changed = old_media != new_media
    alt_changed = old_alt != new_alt

    if not media_changed and not alt_changed:
        # Exact no-op: no write, no promotion, no audit, no updated_at bump.
        tags = repository.list_tags_for_item(db, business_id=business_id, item_id=item_id)
        return _item_summary(item, tags)

    # Classify the change for the audit record (exact presence rules).
    if media_changed and old_media is None:
        change = "attached"
    elif media_changed and new_media is None:
        change = "cleared"
    elif media_changed:
        change = "replaced"
    else:
        change = "alt_updated"

    if new_media is not None and media_changed:
        # Validate same-business + kind + unexpired, and promote to active.
        media_service.claim_for_attachment(db, business_id, new_media)

    item.image_media_id = new_media
    item.image_alt_text = new_alt
    item.updated_at = func.now()
    safe_flush(db)  # a cross-tenant/expired media reference converts to 409
    recorder.record(
        db,
        AuditAction.CATALOG_ITEM_IMAGE_CHANGED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="menu_item",
        target_id=str(item.id),
        details=CatalogItemImageChangedDetails(
            change=change,  # type: ignore[arg-type]
            media_id_old=str(old_media) if old_media is not None else None,
            media_id_new=str(new_media) if new_media is not None else None,
            alt_text_changed="changed" if alt_changed else "unchanged",
        ),
    )
    safe_commit(db)
    db.refresh(item)
    tags = repository.list_tags_for_item(db, business_id=business_id, item_id=item_id)
    return _item_summary(item, tags)
