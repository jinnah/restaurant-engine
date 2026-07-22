"""Catalog persistence access (M3A).

Every read of tenant-owned data takes ``business_id`` (docs/04) — a
repository method without one is invalid by definition. Repositories
never commit (M2A discipline): the catalog service owns the transaction
and the business-row lock that serializes these operations per tenant.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import Session

from app.domains.catalog.models import (
    MenuCategory,
    MenuItem,
    MenuItemDietaryTag,
    ModifierGroup,
    ModifierOption,
)

# --- Categories --------------------------------------------------------------


def add(
    db: Session,
    entity: MenuCategory | MenuItem | MenuItemDietaryTag | ModifierGroup | ModifierOption,
) -> None:
    db.add(entity)


def get_category(
    db: Session, *, business_id: uuid.UUID, category_id: uuid.UUID
) -> MenuCategory | None:
    return db.execute(
        select(MenuCategory).where(
            MenuCategory.business_id == business_id, MenuCategory.id == category_id
        )
    ).scalar_one_or_none()


def list_categories(db: Session, *, business_id: uuid.UUID) -> list[MenuCategory]:
    """All categories in display order (position, then id as a tiebreak)."""
    return list(
        db.execute(
            select(MenuCategory)
            .where(MenuCategory.business_id == business_id)
            .order_by(MenuCategory.position, MenuCategory.id)
        ).scalars()
    )


def count_categories(db: Session, *, business_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count())
        .select_from(MenuCategory)
        .where(MenuCategory.business_id == business_id)
    ).scalar_one()
    return int(count)


def category_name_exists(
    db: Session,
    *,
    business_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Case-insensitive name precheck (friendly error; the index is the law)."""
    query = select(MenuCategory.id).where(
        MenuCategory.business_id == business_id,
        func.lower(MenuCategory.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(MenuCategory.id != exclude_id)
    return db.execute(query.limit(1)).scalar_one_or_none() is not None


def delete_category(db: Session, category: MenuCategory) -> None:
    db.delete(category)


def close_category_position_gap(db: Session, *, business_id: uuid.UUID, position: int) -> None:
    """Shift positions above a removed slot down by one (dense 0..n-1)."""
    db.execute(
        update(MenuCategory)
        .where(MenuCategory.business_id == business_id, MenuCategory.position > position)
        .values(position=MenuCategory.position - 1)
    )


def set_category_positions(
    db: Session, *, business_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    """Assign dense positions 0..n-1 in the given order (deferred unique)."""
    for index, category_id in enumerate(ordered_ids):
        db.execute(
            update(MenuCategory)
            .where(MenuCategory.business_id == business_id, MenuCategory.id == category_id)
            .values(position=index)
        )


# --- Items -------------------------------------------------------------------


def get_item(db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID) -> MenuItem | None:
    return db.execute(
        select(MenuItem).where(MenuItem.business_id == business_id, MenuItem.id == item_id)
    ).scalar_one_or_none()


def list_items(db: Session, *, business_id: uuid.UUID) -> list[MenuItem]:
    """Every item of the business in (category, position, id) order."""
    return list(
        db.execute(
            select(MenuItem)
            .where(MenuItem.business_id == business_id)
            .order_by(MenuItem.category_id, MenuItem.position, MenuItem.id)
        ).scalars()
    )


def list_item_ids_in_category(
    db: Session, *, business_id: uuid.UUID, category_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(MenuItem.id)
            .where(MenuItem.business_id == business_id, MenuItem.category_id == category_id)
            .order_by(MenuItem.position, MenuItem.id)
        ).scalars()
    )


def count_items(db: Session, *, business_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count()).select_from(MenuItem).where(MenuItem.business_id == business_id)
    ).scalar_one()
    return int(count)


def count_items_in_category(db: Session, *, business_id: uuid.UUID, category_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count())
        .select_from(MenuItem)
        .where(MenuItem.business_id == business_id, MenuItem.category_id == category_id)
    ).scalar_one()
    return int(count)


def count_featured_items(db: Session, *, business_id: uuid.UUID) -> int:
    """Featured-flag count for the R1 guard (served by the partial index)."""
    count = db.execute(
        select(func.count())
        .select_from(MenuItem)
        .where(MenuItem.business_id == business_id, MenuItem.is_featured.is_(True))
    ).scalar_one()
    return int(count)


def item_name_exists(
    db: Session,
    *,
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Case-insensitive per-category name precheck (index is the law)."""
    query = select(MenuItem.id).where(
        MenuItem.business_id == business_id,
        MenuItem.category_id == category_id,
        func.lower(MenuItem.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(MenuItem.id != exclude_id)
    return db.execute(query.limit(1)).scalar_one_or_none() is not None


def delete_item(db: Session, item: MenuItem) -> None:
    db.delete(item)


def close_item_position_gap(
    db: Session, *, business_id: uuid.UUID, category_id: uuid.UUID, position: int
) -> None:
    db.execute(
        update(MenuItem)
        .where(
            MenuItem.business_id == business_id,
            MenuItem.category_id == category_id,
            MenuItem.position > position,
        )
        .values(position=MenuItem.position - 1)
    )


def set_item_positions(
    db: Session,
    *,
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    ordered_ids: list[uuid.UUID],
) -> None:
    for index, item_id in enumerate(ordered_ids):
        db.execute(
            update(MenuItem)
            .where(
                MenuItem.business_id == business_id,
                MenuItem.category_id == category_id,
                MenuItem.id == item_id,
            )
            .values(position=index)
        )


# --- Dietary tags ------------------------------------------------------------


def list_tags_for_item(db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID) -> list[str]:
    return list(
        db.execute(
            select(MenuItemDietaryTag.tag)
            .where(
                MenuItemDietaryTag.business_id == business_id,
                MenuItemDietaryTag.item_id == item_id,
            )
            .order_by(MenuItemDietaryTag.tag)
        ).scalars()
    )


def list_tags_for_business(db: Session, *, business_id: uuid.UUID) -> dict[uuid.UUID, list[str]]:
    """All (item_id → tags) of one business, tag-sorted, for the menu view."""
    rows = db.execute(
        select(MenuItemDietaryTag.item_id, MenuItemDietaryTag.tag)
        .where(MenuItemDietaryTag.business_id == business_id)
        .order_by(MenuItemDietaryTag.item_id, MenuItemDietaryTag.tag)
    ).all()
    tags_by_item: dict[uuid.UUID, list[str]] = {}
    for item_id, tag in rows:
        tags_by_item.setdefault(item_id, []).append(tag)
    return tags_by_item


def replace_item_tags(
    db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID, tags: Sequence[str]
) -> None:
    """Replace an item's tag set (delete-and-insert inside the caller's txn)."""
    db.execute(
        delete(MenuItemDietaryTag).where(
            MenuItemDietaryTag.business_id == business_id,
            MenuItemDietaryTag.item_id == item_id,
        )
    )
    for tag in tags:
        db.add(MenuItemDietaryTag(business_id=business_id, item_id=item_id, tag=tag))


# --- Modifier groups (M3B) ----------------------------------------------------


def get_group(db: Session, *, business_id: uuid.UUID, group_id: uuid.UUID) -> ModifierGroup | None:
    return db.execute(
        select(ModifierGroup).where(
            ModifierGroup.business_id == business_id, ModifierGroup.id == group_id
        )
    ).scalar_one_or_none()


def list_groups_for_item(
    db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID
) -> list[ModifierGroup]:
    """The item's groups in display order (position, then id tiebreak)."""
    return list(
        db.execute(
            select(ModifierGroup)
            .where(ModifierGroup.business_id == business_id, ModifierGroup.item_id == item_id)
            .order_by(ModifierGroup.position, ModifierGroup.id)
        ).scalars()
    )


def list_group_ids_for_item(
    db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(ModifierGroup.id)
            .where(ModifierGroup.business_id == business_id, ModifierGroup.item_id == item_id)
            .order_by(ModifierGroup.position, ModifierGroup.id)
        ).scalars()
    )


def count_groups_for_item(db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count())
        .select_from(ModifierGroup)
        .where(ModifierGroup.business_id == business_id, ModifierGroup.item_id == item_id)
    ).scalar_one()
    return int(count)


def count_groups_for_business(db: Session, *, business_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count())
        .select_from(ModifierGroup)
        .where(ModifierGroup.business_id == business_id)
    ).scalar_one()
    return int(count)


def group_name_exists(
    db: Session,
    *,
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Case-insensitive per-item group-name precheck (index is the law)."""
    query = select(ModifierGroup.id).where(
        ModifierGroup.business_id == business_id,
        ModifierGroup.item_id == item_id,
        func.lower(ModifierGroup.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(ModifierGroup.id != exclude_id)
    return db.execute(query.limit(1)).scalar_one_or_none() is not None


def delete_group(db: Session, group: ModifierGroup) -> None:
    db.delete(group)


def close_group_position_gap(
    db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID, position: int
) -> None:
    db.execute(
        update(ModifierGroup)
        .where(
            ModifierGroup.business_id == business_id,
            ModifierGroup.item_id == item_id,
            ModifierGroup.position > position,
        )
        .values(position=ModifierGroup.position - 1)
    )


def set_group_positions(
    db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    for index, group_id in enumerate(ordered_ids):
        db.execute(
            update(ModifierGroup)
            .where(
                ModifierGroup.business_id == business_id,
                ModifierGroup.item_id == item_id,
                ModifierGroup.id == group_id,
            )
            .values(position=index)
        )


# --- Modifier options (M3B) ---------------------------------------------------


def get_option(
    db: Session, *, business_id: uuid.UUID, option_id: uuid.UUID
) -> ModifierOption | None:
    return db.execute(
        select(ModifierOption).where(
            ModifierOption.business_id == business_id, ModifierOption.id == option_id
        )
    ).scalar_one_or_none()


def list_options_for_group(
    db: Session, *, business_id: uuid.UUID, group_id: uuid.UUID
) -> list[ModifierOption]:
    return list(
        db.execute(
            select(ModifierOption)
            .where(ModifierOption.business_id == business_id, ModifierOption.group_id == group_id)
            .order_by(ModifierOption.position, ModifierOption.id)
        ).scalars()
    )


def list_options_for_groups(
    db: Session, *, business_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ModifierOption]]:
    """All (group_id -> ordered options) for the per-item tree view."""
    if not group_ids:
        return {}
    rows = db.execute(
        select(ModifierOption)
        .where(ModifierOption.business_id == business_id, ModifierOption.group_id.in_(group_ids))
        .order_by(ModifierOption.group_id, ModifierOption.position, ModifierOption.id)
    ).scalars()
    options_by_group: dict[uuid.UUID, list[ModifierOption]] = {}
    for option in rows:
        options_by_group.setdefault(option.group_id, []).append(option)
    return options_by_group


def list_option_ids_for_group(
    db: Session, *, business_id: uuid.UUID, group_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(ModifierOption.id)
            .where(ModifierOption.business_id == business_id, ModifierOption.group_id == group_id)
            .order_by(ModifierOption.position, ModifierOption.id)
        ).scalars()
    )


def count_options_for_group(db: Session, *, business_id: uuid.UUID, group_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count())
        .select_from(ModifierOption)
        .where(ModifierOption.business_id == business_id, ModifierOption.group_id == group_id)
    ).scalar_one()
    return int(count)


def count_options_for_business(db: Session, *, business_id: uuid.UUID) -> int:
    count = db.execute(
        select(func.count())
        .select_from(ModifierOption)
        .where(ModifierOption.business_id == business_id)
    ).scalar_one()
    return int(count)


def option_name_exists(
    db: Session,
    *,
    business_id: uuid.UUID,
    group_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Case-insensitive per-group option-name precheck (index is the law)."""
    query = select(ModifierOption.id).where(
        ModifierOption.business_id == business_id,
        ModifierOption.group_id == group_id,
        func.lower(ModifierOption.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(ModifierOption.id != exclude_id)
    return db.execute(query.limit(1)).scalar_one_or_none() is not None


def delete_option(db: Session, option: ModifierOption) -> None:
    db.delete(option)


def close_option_position_gap(
    db: Session, *, business_id: uuid.UUID, group_id: uuid.UUID, position: int
) -> None:
    db.execute(
        update(ModifierOption)
        .where(
            ModifierOption.business_id == business_id,
            ModifierOption.group_id == group_id,
            ModifierOption.position > position,
        )
        .values(position=ModifierOption.position - 1)
    )


def set_option_positions(
    db: Session, *, business_id: uuid.UUID, group_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    for index, option_id in enumerate(ordered_ids):
        db.execute(
            update(ModifierOption)
            .where(
                ModifierOption.business_id == business_id,
                ModifierOption.group_id == group_id,
                ModifierOption.id == option_id,
            )
            .values(position=index)
        )


# --- Public projection reads (M3D) --------------------------------------------
#
# Public reads filter in SQL rather than loading the administrative tree and
# discarding rows: hidden items' dietary, modifier, and media data are never
# read at all. Every list takes the parent ids already established as
# publicly eligible, so child rows load only for relevant parents and the
# statement count does not grow with the number of parents.


def list_visible_categories(db: Session, *, business_id: uuid.UUID) -> list[MenuCategory]:
    """Publicly visible categories in display order."""
    return list(
        db.execute(
            select(MenuCategory)
            .where(MenuCategory.business_id == business_id, MenuCategory.is_visible.is_(True))
            .order_by(MenuCategory.position, MenuCategory.id)
        ).scalars()
    )


def list_public_items(
    db: Session, *, business_id: uuid.UUID, category_ids: list[uuid.UUID]
) -> list[MenuItem]:
    """Non-hidden items of the given visible categories, in display order."""
    if not category_ids:
        return []
    return list(
        db.execute(
            select(MenuItem)
            .where(
                MenuItem.business_id == business_id,
                MenuItem.is_hidden.is_(False),
                MenuItem.category_id.in_(category_ids),
            )
            .order_by(MenuItem.category_id, MenuItem.position, MenuItem.id)
        ).scalars()
    )


def list_tags_for_items(
    db: Session, *, business_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """(item_id -> tags) for the given items only, tag-ascending."""
    if not item_ids:
        return {}
    rows = db.execute(
        select(MenuItemDietaryTag.item_id, MenuItemDietaryTag.tag)
        .where(
            MenuItemDietaryTag.business_id == business_id,
            MenuItemDietaryTag.item_id.in_(item_ids),
        )
        .order_by(MenuItemDietaryTag.item_id, MenuItemDietaryTag.tag)
    ).all()
    tags_by_item: dict[uuid.UUID, list[str]] = {}
    for item_id, tag in rows:
        tags_by_item.setdefault(item_id, []).append(tag)
    return tags_by_item


def list_groups_for_items(
    db: Session, *, business_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ModifierGroup]]:
    """(item_id -> ordered groups) for the given items only."""
    if not item_ids:
        return {}
    rows = db.execute(
        select(ModifierGroup)
        .where(ModifierGroup.business_id == business_id, ModifierGroup.item_id.in_(item_ids))
        .order_by(ModifierGroup.item_id, ModifierGroup.position, ModifierGroup.id)
    ).scalars()
    groups_by_item: dict[uuid.UUID, list[ModifierGroup]] = {}
    for group in rows:
        groups_by_item.setdefault(group.item_id, []).append(group)
    return groups_by_item


def list_available_options_for_groups(
    db: Session, *, business_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ModifierOption]]:
    """(group_id -> ordered **available** options) for the given groups.

    Unavailable options never reach the public projection, so they are
    excluded in SQL — the returned count is exactly the active-option
    count the satisfiability policy consumes.
    """
    if not group_ids:
        return {}
    rows = db.execute(
        select(ModifierOption)
        .where(
            ModifierOption.business_id == business_id,
            ModifierOption.is_available.is_(True),
            ModifierOption.group_id.in_(group_ids),
        )
        .order_by(ModifierOption.group_id, ModifierOption.position, ModifierOption.id)
    ).scalars()
    options_by_group: dict[uuid.UUID, list[ModifierOption]] = {}
    for option in rows:
        options_by_group.setdefault(option.group_id, []).append(option)
    return options_by_group


def media_is_publicly_attached(db: Session, *, business_id: uuid.UUID, media_id: uuid.UUID) -> bool:
    """Does a currently public menu item of this business show this asset?

    The M3D public-media authorization predicate (ADR-017): an asset is
    publicly deliverable only while at least one non-hidden item in a
    visible category references it. ``status = 'active'`` alone is
    deliberately insufficient — promotion is one-way, so a detached asset
    would otherwise stay retrievable forever by anyone holding its URL.
    Sold-out and non-orderable items still authorize their image.

    One bounded tenant-scoped ``EXISTS``; the result is a boolean, so no
    attachment detail can leak into a response.
    """
    predicate = exists(
        select(MenuItem.id)
        .join(
            MenuCategory,
            (MenuCategory.business_id == MenuItem.business_id)
            & (MenuCategory.id == MenuItem.category_id),
        )
        .where(
            MenuItem.business_id == business_id,
            MenuItem.image_media_id == media_id,
            MenuItem.is_hidden.is_(False),
            MenuCategory.is_visible.is_(True),
        )
    )
    return bool(db.execute(select(predicate)).scalar_one())
