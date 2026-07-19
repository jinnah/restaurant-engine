"""Catalog persistence access (M3A).

Every read of tenant-owned data takes ``business_id`` (docs/04) — a
repository method without one is invalid by definition. Repositories
never commit (M2A discipline): the catalog service owns the transaction
and the business-row lock that serializes these operations per tenant.
"""

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.domains.catalog.models import MenuCategory, MenuItem, MenuItemDietaryTag

# --- Categories --------------------------------------------------------------


def add(db: Session, entity: MenuCategory | MenuItem | MenuItemDietaryTag) -> None:
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
    db: Session, *, business_id: uuid.UUID, item_id: uuid.UUID, tags: list[str]
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
