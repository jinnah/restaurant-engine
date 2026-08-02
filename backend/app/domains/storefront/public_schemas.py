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
from app.domains.storefront.theme_registries import PaletteId, TypePairingId
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


class PublicHoursSectionProps(BaseModel):
    """Hours section: presentation choices only (ADR-025 D5).

    Carries **no** schedule — the renderer composes this section with the
    public availability projection (`public_availability_get`), which
    remains the single source of the weekly schedule, exceptions, and the
    live open/closed facts. `show_open_now` is the owner's display choice
    for the status line, not a computed fact.
    """

    heading: str
    intro: str | None
    show_open_now: bool


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


class PublicHoursSection(BaseModel):
    id: str
    type: Literal[SectionType.HOURS]
    props: PublicHoursSectionProps


AnyPublicSection = (
    PublicHeroSection
    | PublicMenuSection
    | PublicStorySection
    | PublicContactSection
    | PublicGallerySection
    | PublicHoursSection
)

# The discriminated form used as the field annotation (the sections.py
# convention), so the OpenAPI document and the generated client see a
# discriminated union rather than a bare anyOf.
PublicSection = Annotated[AnyPublicSection, Field(discriminator="type")]


class PublicThemeLogo(BaseModel):
    """The tenant logo: renditions and true dimensions, and **no alt text**.

    ADR-024 §7 rules the logo permanently decorative: it renders `alt=""`
    beside the business name, which stays the visible semantic `h1` in every
    variant. Omitting `alt_text` here makes that ruling structural rather
    than advisory — there is no value a renderer could pass through by
    mistake, and a null one would produce an *unlabelled* image rather than
    a decorative one. This is the projection-side counterpart of
    `ThemeLogo` carrying no `alt_text`.

    Intrinsic `width`/`height` are present for the same reason every other
    image descriptor carries them: the box is reserved before the image
    loads, so the header never shifts (no CLS).
    """

    width: int
    height: int
    url: str
    variants: list[PublicStorefrontImageVariant]


class PublicTheme(BaseModel):
    """The tenant-adjustable presentation tokens of a rendered version.

    `accent` is the tenant's single arbitrary token; `palette` and
    `type_pairing` are selections from the closed platform registries, so a
    renderer maps them to tokens through an exhaustive table and can never
    receive an unregistered value from a 200 response (ADR-024 §3).

    These tokens are stored inside the version row's configuration, so a
    published or archived version projects the tokens it was published
    with — the design-variant precedent extended to the whole visual
    surface (ADR-024 §10).

    `logo` is null when the version sets none, and also when its asset is no
    longer renderable: a reference that cannot resolve degrades to absence
    rather than a dead URL, and the business name is always present as text.
    """

    accent: str
    palette: PaletteId
    type_pairing: TypePairingId
    logo: PublicThemeLogo | None


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
