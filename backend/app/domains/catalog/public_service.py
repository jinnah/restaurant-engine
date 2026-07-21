"""Public menu projection (M3D, ADR-017).

The unauthenticated read side of the catalog. There is no actor, no
capability check, and no lock: the Business arrives already resolved from
the request Host (ADR-013), and every repository call is scoped to its
``business_id``.

**Persisted validity vs. computed public availability.** The database
decides what may be *stored*; this module decides what a guest may
currently *see and order*. Nothing here is a write gate — an item whose
required modifier group has no available options is still perfectly legal
administratively, it simply projects as non-orderable.

**Defensive assembly under READ COMMITTED.** Each statement sees its own
snapshot, so a concurrent administrative commit can land between reads.
Children are therefore attached only to parents present in *this*
projection (dictionary lookups keyed by ids already loaded), never by
dereferencing a foreign key that may have vanished. The result may be
momentarily stale, but it is always structurally valid: no dangling
reference, no cross-tenant row, and no exception from a disappearing
parent.
"""

import uuid

from sqlalchemy.orm import Session

from app.domains.businesses.resolution import ResolvedBusiness
from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.catalog import dietary, policies, repository
from app.domains.catalog.models import MenuCategory, MenuItem, ModifierGroup, ModifierOption
from app.domains.catalog.public_schemas import (
    PublicMenu,
    PublicMenuCategory,
    PublicMenuImage,
    PublicMenuImageVariant,
    PublicMenuItem,
    PublicModifierGroup,
    PublicModifierOption,
)
from app.domains.media import public_service as media_public
from app.domains.media.models import MediaAsset, MediaAssetVariant


def media_is_publicly_visible(db: Session, *, business_id: uuid.UUID, media_id: uuid.UUID) -> bool:
    """Is this media asset currently shown by a public menu item?

    Catalog owns this question because the attachment is a catalog fact
    (``menu_items.image_media_id``) governed by catalog visibility rules.
    The public media endpoint composes it with media's own inventory check
    at the application layer, so media never imports catalog (ADR-017 M3C
    final correction M).

    An asset detached after promotion, or one left referenced only by
    hidden items or items in invisible categories, is not publicly
    visible: ``status = 'active'`` is one-way, so without this check such
    an asset would stay retrievable forever by anyone holding its URL.
    """
    return repository.media_is_publicly_attached(db, business_id=business_id, media_id=media_id)


def _option_view(option: ModifierOption) -> PublicModifierOption:
    return PublicModifierOption(
        id=option.id,
        name=option.name,
        price_delta_minor=option.price_delta_minor,
    )


def _group_view(group: ModifierGroup, options: list[ModifierOption]) -> PublicModifierGroup:
    return PublicModifierGroup(
        id=group.id,
        name=group.name,
        min_select=group.min_select,
        max_select=group.max_select,
        options=[_option_view(option) for option in options],
    )


def _project_groups(
    groups: list[ModifierGroup],
    options_by_group: dict[uuid.UUID, list[ModifierOption]],
) -> tuple[list[PublicModifierGroup], bool]:
    """Publicly renderable groups, and whether a required one was dropped.

    Satisfiability is the shared policy formula (``is_group_satisfiable``,
    ADR-017 D5) computed over the **available** options only — the same
    formula the administrative projection uses, never a second copy.

    An unsatisfiable group is omitted rather than returned disabled: a
    guest cannot complete it, so it is not renderable information. Whether
    that omission also blocks ordering depends on the group: an optional
    group (``min_select == 0``) is harmless, a required one is not.
    """
    views: list[PublicModifierGroup] = []
    required_dropped = False
    for group in groups:
        options = options_by_group.get(group.id, [])
        if policies.is_group_satisfiable(group.min_select, group.max_select, len(options)):
            views.append(_group_view(group, options))
        elif group.min_select >= 1:
            required_dropped = True
    return views, required_dropped


def _image_view(
    item: MenuItem, asset: MediaAsset, variants: list[MediaAssetVariant]
) -> PublicMenuImage:
    """Describe an item's image by URL and true pixel dimensions.

    The alt text belongs to the *attachment*, not the asset (ADR-017 M3C),
    so it comes from the item. No asset id, key, path, or checksum is
    exposed: the URL is the resource identity.
    """
    return PublicMenuImage(
        alt_text=item.image_alt_text,
        width=asset.width,
        height=asset.height,
        url=media_public.public_media_url(asset.id, media_public.CANONICAL_VARIANT),
        variants=[
            PublicMenuImageVariant(
                variant=variant.variant,  # type: ignore[arg-type]
                width=variant.width,
                height=variant.height,
                url=media_public.public_media_url(asset.id, variant.variant),
            )
            for variant in variants
        ],
    )


def _item_view(
    item: MenuItem,
    tags: list[str],
    groups: list[PublicModifierGroup],
    image: PublicMenuImage | None,
    *,
    required_group_unsatisfiable: bool,
) -> PublicMenuItem:
    # Dietary reads are fail-closed (D6): a stored value outside the
    # registry is never surfaced, publicly least of all.
    return PublicMenuItem(
        id=item.id,
        name=item.name,
        description=item.description,
        price_minor=item.price_minor,
        is_available=item.is_available,
        is_orderable=item.is_available and not required_group_unsatisfiable,
        dietary_tags=dietary.filter_known(tags),
        image=image,
        modifier_groups=groups,
    )


def _category_view(category: MenuCategory, items: list[PublicMenuItem]) -> PublicMenuCategory:
    return PublicMenuCategory(
        id=category.id,
        name=category.name,
        description=category.description,
        items=items,
    )


def get_public_menu(db: Session, business: ResolvedBusiness) -> PublicMenu:
    """The complete public menu of an already-resolved active Business.

    Visibility: invisible categories and hidden items are excluded, and a
    category left with no publicly eligible item is suppressed rather than
    rendered as an empty section.

    Query shape: categories, then items for those categories, then tags,
    groups, and options for the items that survived — child statements are
    skipped entirely when their parent set is empty, so a small menu costs
    fewer statements than a large one and no statement count grows with
    the number of parents.
    """
    categories = repository.list_visible_categories(db, business_id=business.business_id)
    category_ids = [category.id for category in categories]
    items = repository.list_public_items(
        db, business_id=business.business_id, category_ids=category_ids
    )
    item_ids = [item.id for item in items]

    tags_by_item = repository.list_tags_for_items(
        db, business_id=business.business_id, item_ids=item_ids
    )
    groups_by_item = repository.list_groups_for_items(
        db, business_id=business.business_id, item_ids=item_ids
    )
    group_ids = [group.id for groups in groups_by_item.values() for group in groups]
    options_by_group = repository.list_available_options_for_groups(
        db, business_id=business.business_id, group_ids=group_ids
    )

    # Images are described only for items that survived visibility, and only
    # for assets confirmed active in this same projection: an item whose
    # asset is pending or gone projects without an image rather than
    # advertising a URL that would answer 404.
    image_ids = [item.image_media_id for item in items if item.image_media_id is not None]
    assets, variants_by_asset = media_public.list_public_representations(
        db, business_id=business.business_id, asset_ids=image_ids
    )

    items_by_category: dict[uuid.UUID, list[PublicMenuItem]] = {}
    featured_ids: set[uuid.UUID] = set()
    for item in items:
        groups, required_dropped = _project_groups(
            groups_by_item.get(item.id, []), options_by_group
        )
        asset = assets.get(item.image_media_id) if item.image_media_id is not None else None
        image = (
            _image_view(item, asset, variants_by_asset.get(asset.id, []))
            if asset is not None
            else None
        )
        if item.is_featured:
            featured_ids.add(item.id)
        items_by_category.setdefault(item.category_id, []).append(
            _item_view(
                item,
                tags_by_item.get(item.id, []),
                groups,
                image,
                required_group_unsatisfiable=required_dropped,
            )
        )

    category_views = [
        _category_view(category, items_by_category[category.id])
        for category in categories
        # Suppress a category with no publicly eligible item: an empty
        # section reads as broken on a storefront.
        if items_by_category.get(category.id)
    ]
    return PublicMenu(
        business=PublicSiteSummary(
            name=business.name,
            slug=business.slug,
            timezone=business.timezone,
            currency=business.currency,
        ),
        categories=category_views,
        featured_item_ids=_featured_ids(category_views, featured_ids),
    )


def _featured_ids(
    categories: list[PublicMenuCategory], featured: set[uuid.UUID]
) -> list[uuid.UUID]:
    """Featured ids in menu order, bounded by the featured policy.

    Ids only, never duplicated item objects — those would drag whole
    modifier trees along and invite the two copies to drift. Derived from
    the assembled tree, so a featured id can only ever name an item
    actually present in it, ordered by category position then item
    position.

    The bound is applied here as well as at write time. The service caps
    featured items under the Business row lock, so a compliant database
    can never exceed it; but legacy, imported, or directly manipulated
    rows are outside that guarantee, and the public contract promises at
    most ``MAX_FEATURED_ITEMS``. Truncating the already-ordered list keeps
    the promise without a repair, an extra query, or a second constant —
    it reuses the same policy the write path enforces.
    """
    ordered = [item.id for category in categories for item in category.items if item.id in featured]
    return ordered[: policies.MAX_FEATURED_ITEMS]
