"""The catalog checkout view (M6A, ADR-026 — blueprint §6.2).

Orders must revalidate and reprice a cart against the *current* catalog
at order time, but a domain never reaches into another domain's models
for hidden business logic. This module is catalog's explicit answer: a
frozen, read-only snapshot of exactly the facts checkout needs, assembled
by catalog with catalog's own repository and policy — the same visibility
and satisfiability rules the public menu projection applies, restated as
data rather than re-derived by the caller.

The view is deliberately *not* the public projection: checkout needs the
unavailable options too (to say "that option is gone" rather than "no
such option") and needs per-item facts for items a stale cart references
even when the projection would have dropped them.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domains.catalog import policies, repository


@dataclass(frozen=True)
class CheckoutOption:
    """One modifier option as checkout needs it."""

    id: uuid.UUID
    name: str
    price_delta_minor: int
    is_available: bool


@dataclass(frozen=True)
class CheckoutGroup:
    """One modifier group with its full option set and selection rules."""

    id: uuid.UUID
    name: str
    min_select: int
    max_select: int | None
    options: tuple[CheckoutOption, ...]

    @property
    def is_required(self) -> bool:
        return self.min_select >= 1

    @property
    def active_option_count(self) -> int:
        return sum(1 for option in self.options if option.is_available)

    @property
    def is_satisfiable(self) -> bool:
        return policies.is_group_satisfiable(
            self.min_select, self.max_select, self.active_option_count
        )


@dataclass(frozen=True)
class CheckoutItem:
    """One menu item as checkout needs it.

    ``is_publicly_visible`` folds the projection's exclusion rules (hidden
    item, invisible category); ``is_available`` is the sold-out-today
    flag. Orderability is the caller's judgment over these plus the
    groups — the same formula as the public ``is_orderable``, applied at
    order time.
    """

    id: uuid.UUID
    display_name: str
    price_minor: int
    is_publicly_visible: bool
    is_available: bool
    groups: tuple[CheckoutGroup, ...]


def checkout_view(
    db: Session, *, business_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, CheckoutItem]:
    """The checkout facts for exactly the requested items.

    An unknown or cross-business item id is simply absent from the result
    — the caller reports it as a stale line, and no existence beyond this
    business is ever disclosed. Ordering of the result is irrelevant; the
    cart's order governs.
    """
    view: dict[uuid.UUID, CheckoutItem] = {}
    distinct_ids = list(dict.fromkeys(item_ids))
    if not distinct_ids:
        return view
    groups_by_item = repository.list_groups_for_items(
        db, business_id=business_id, item_ids=distinct_ids
    )
    all_group_ids = [group.id for groups in groups_by_item.values() for group in groups]
    options_by_group = repository.list_options_for_groups(
        db, business_id=business_id, group_ids=all_group_ids
    )
    for item_id in distinct_ids:
        item = repository.get_item(db, business_id=business_id, item_id=item_id)
        if item is None:
            continue
        category = repository.get_category(
            db, business_id=business_id, category_id=item.category_id
        )
        visible = category is not None and category.is_visible and not item.is_hidden
        groups = tuple(
            CheckoutGroup(
                id=group.id,
                name=group.name,
                min_select=group.min_select,
                max_select=group.max_select,
                options=tuple(
                    CheckoutOption(
                        id=option.id,
                        name=option.name,
                        price_delta_minor=option.price_delta_minor,
                        is_available=option.is_available,
                    )
                    for option in options_by_group.get(group.id, [])
                ),
            )
            for group in groups_by_item.get(item_id, [])
        )
        view[item_id] = CheckoutItem(
            id=item.id,
            display_name=item.name,
            price_minor=item.price_minor,
            is_publicly_visible=visible,
            is_available=item.is_available,
            groups=groups,
        )
    return view
