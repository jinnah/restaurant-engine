"""Public menu projection schemas (M3D, ADR-017).

Deliberately **separate** from the administrative schemas rather than
reusing them: `ItemSummary`, `ModifierGroupView`, and `ModifierOptionView`
carry management-only fields (`position`, `is_hidden`, `is_featured`,
`image_media_id`, `active_option_count`, `is_satisfiable`, timestamps) that
must never reach an unauthenticated consumer. Reuse would make every future
administrative field a public-disclosure decision.

Only `PublicSiteSummary` is shared, because it is already the public
Business projection (ADR-013) and is the **sole** source of currency here —
prices are integer minor units and the currency is never repeated per item
(ADR-017 D8).

Ordering is the contract: collections arrive in display order, so no
`position` is exposed. Items appear exactly once, inside their category;
`featured_item_ids` references those canonical representations by id rather
than duplicating item objects (and with them whole modifier trees).
"""

import uuid
from typing import Literal

from pydantic import BaseModel

from app.domains.businesses.schemas import PublicSiteSummary


class PublicModifierOption(BaseModel):
    """One selectable option (available options only).

    Unavailable options are omitted from the projection entirely, so no
    availability flag is needed: everything present is selectable.
    """

    id: uuid.UUID
    name: str
    price_delta_minor: int


class PublicModifierGroup(BaseModel):
    """One customization group a guest can currently complete.

    Only satisfiable groups are projected, so `is_satisfiable` and
    `active_option_count` (administrative diagnostics) are absent —
    `options` is exactly the selectable set. `max_select` null means
    unlimited by configuration.
    """

    id: uuid.UUID
    name: str
    min_select: int
    max_select: int | None
    options: list[PublicModifierOption]


class PublicMenuImageVariant(BaseModel):
    """One responsive rendition, with its true pixel dimensions.

    The client selects a rendition (``srcset``); the API publishes every
    one it has. `url` is relative — the storefront is served same-origin
    with the tenant host (ADR-013).
    """

    variant: Literal["w320", "w640", "w1280"]
    width: int
    height: int
    url: str


class PublicMenuImage(BaseModel):
    """The item's image: canonical dimensions plus responsive renditions.

    Carries no asset id, storage key, path, or checksum — the URL is the
    resource identity (ADR-017 R3). `alt_text` is the contextual alt text
    of this attachment, not a property of the asset, and may be null.
    """

    alt_text: str | None
    width: int
    height: int
    url: str
    variants: list[PublicMenuImageVariant]


class PublicMenuItem(BaseModel):
    """One publicly visible menu item.

    `is_available` is the "sold out today" state; a sold-out item stays
    listed. `is_orderable` is computed: available **and** every required
    modifier group currently satisfiable. M6 remains authoritative at
    order time — these are display facts, not a checkout guarantee.
    """

    id: uuid.UUID
    name: str
    description: str | None
    price_minor: int
    is_available: bool
    is_orderable: bool
    dietary_tags: list[str]
    image: PublicMenuImage | None
    modifier_groups: list[PublicModifierGroup]


class PublicMenuCategory(BaseModel):
    """One visible menu section with at least one publicly visible item."""

    id: uuid.UUID
    name: str
    description: str | None
    items: list[PublicMenuItem]


class PublicMenu(BaseModel):
    """The complete public menu of the host-resolved Business.

    `business` is the sole source of name, slug, timezone, and currency.
    `featured_item_ids` lists at most the featured-policy maximum and
    refers only to items present in `categories`.
    """

    business: PublicSiteSummary
    categories: list[PublicMenuCategory]
    featured_item_ids: list[uuid.UUID]
