"""Public storefront projection schemas (M4C, ADR-020 §9, §12).

Deliberately **separate** from the administrative schemas rather than
reusing them: `DraftView`, `VersionSummary`, and the persisted
`StorefrontConfig` carry management-only facts (lock versions, version
numbers, states, publisher identity, provenance, timestamps, raw media
asset ids) that must never reach an unauthenticated consumer. Reuse would
make every future administrative field a public-disclosure decision.

Only `PublicSiteSummary` is shared, because it is already the public
Business projection (ADR-013) — the same single source of name, slug,
timezone, and currency the public menu uses.

The projection is what a renderer needs and nothing else: the published
design variant, the theme tokens, and the **enabled** sections in display
order, with every media reference resolved to URL descriptors (the
`PublicMenuImage` convention — no asset id, storage key, path, or
checksum; the URL is the resource identity). Array order is the contract,
so no position or enabled flag is exposed: everything present is enabled.

The authenticated draft preview (ADR-020 §9) returns this same shape so
the M4D public renderer and the M4E workspace preview share one stable
component-facing contract; only the image URLs differ (preview addresses
the authenticated member media route).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.storefront.sections import HeroAction, SectionType
from app.domains.storefront.variants import DesignVariant


class PublicStorefrontImageVariant(BaseModel):
    """One responsive rendition, with its true pixel dimensions.

    The client selects a rendition (``srcset``); the API publishes every
    one it has. `url` is relative — the storefront is served same-origin
    with the tenant host (ADR-013).
    """

    variant: Literal["w320", "w640", "w1280"]
    width: int
    height: int
    url: str


class PublicStorefrontImage(BaseModel):
    """A section's image: canonical dimensions plus responsive renditions.

    Carries no asset id, storage key, path, or checksum — the URL is the
    resource identity (ADR-017 R3). `alt_text` is the contextual alt text
    of this placement, not a property of the asset, and may be null.
    """

    alt_text: str | None
    width: int
    height: int
    url: str
    variants: list[PublicStorefrontImageVariant]


class PublicHeroProps(BaseModel):
    """Opening section: headline, optional supporting line, optional image."""

    heading: str
    subheading: str | None
    image: PublicStorefrontImage | None
    primary_action: HeroAction


class PublicMenuSectionProps(BaseModel):
    """Menu section: heading and optional introduction.

    Carries **no** menu content — the renderer composes this section with
    the existing public menu projection (`public_menu_get`), which remains
    the single source of items, ordering, and featured status.
    """

    heading: str
    intro: str | None


class PublicStoryProps(BaseModel):
    """The business's story: heading plus multi-paragraph plain text."""

    heading: str
    body: str


class PublicContactProps(BaseModel):
    """Contact details as structured fields (no hours — M5)."""

    heading: str
    address_lines: list[str]
    phone: str | None
    email: str | None


class PublicGalleryProps(BaseModel):
    """A bounded set of resolved images, in display order.

    Only images whose assets are currently renderable are present — a
    reference whose asset is gone degrades by omission rather than
    advertising a URL that would answer 404.
    """

    heading: str | None
    images: list[PublicStorefrontImage]


class PublicHeroSection(BaseModel):
    id: str
    type: Literal[SectionType.HERO]
    props: PublicHeroProps


class PublicMenuSection(BaseModel):
    id: str
    type: Literal[SectionType.MENU]
    props: PublicMenuSectionProps


class PublicStorySection(BaseModel):
    id: str
    type: Literal[SectionType.STORY]
    props: PublicStoryProps


class PublicContactSection(BaseModel):
    id: str
    type: Literal[SectionType.CONTACT]
    props: PublicContactProps


class PublicGallerySection(BaseModel):
    id: str
    type: Literal[SectionType.GALLERY]
    props: PublicGalleryProps


AnyPublicSection = (
    PublicHeroSection
    | PublicMenuSection
    | PublicStorySection
    | PublicContactSection
    | PublicGallerySection
)

# The discriminated form used as the field annotation (the sections.py
# convention), so the OpenAPI document and the generated client see a
# discriminated union rather than a bare anyOf.
PublicSection = Annotated[AnyPublicSection, Field(discriminator="type")]


class PublicTheme(BaseModel):
    """The tenant-adjustable presentation tokens (one accent in M4)."""

    accent: str


class PublicStorefront(BaseModel):
    """The published storefront of the host-resolved Business.

    `business` is the sole source of name, slug, timezone, and currency
    (the public menu convention). `sections` contains the **enabled**
    sections of the currently published version, in display order — array
    order is the contract. No version number, state, publisher, timestamp,
    lock, or provenance fact is exposed: a 200 already proves a published
    storefront exists, and everything else is administrative.
    """

    business: PublicSiteSummary
    design_variant: DesignVariant
    theme: PublicTheme
    sections: list[PublicSection]
