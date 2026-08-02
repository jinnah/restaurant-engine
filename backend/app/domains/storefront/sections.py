"""Section registry (M4A, ADR-020).

The code-owned, closed set of section types a storefront may contain, as a
**typed discriminated union** on ``type``. A section the registry does not
declare cannot be validated, stored, or rendered, and adding one is a
reviewed code change — never tenant input.

The persisted shape is the blueprint §7.4 contract, unchanged::

    {"id": "hero-main", "type": "hero", "enabled": true, "props": {}}

Five types ship in M4 (ruling D1): hero, menu, story, contact, gallery.
M5D registers the sixth (ADR-025 D5): hours — presentation choices only,
with the schedule itself arriving from the availability projection at
render time, exactly as the menu section composes with the public menu.

What is deliberately **absent**, and must not be smuggled into a generic
field later:

* **hours data** — the ``hours`` section carries a heading, an optional
  intro, and one display toggle, and **no schedule of any kind**: no
  intervals, no dates, no timezone, and no free-text "Mon-Fri 9-5" line
  (the freeform storefront text docs/03 forbids). The structured hours
  live in the hours domain and reach the page through
  ``GET /api/v1/public/availability``; storing them here would create a
  second source of truth and freeze live operational data into published
  history (ADR-025 D5);
* **ordering** — no ordering section and no "Order Online" action. The
  hero's ``primary_action`` is a closed enum whose only non-empty member is
  ``view_menu``, ordinary navigation to the menu. M6 extends that enum with
  an entitlement-gated ordering member; M10 registers campaign placements.
  Extending the enum or registering a type is the entire extension
  mechanism;
* **prices** — items are referenced by the menu projection at render time,
  never priced or copied here (Orders owns snapshots, M6);
* **rich text, HTML, CSS, JavaScript** — every copy field is plain text
  (blueprint §12.3).

Media is referenced by asset id only. M4A validates **shape**; that an
asset exists, belongs to this business, and is claimable is a service
question requiring the database, and belongs to M4B.
"""

import re
import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.domains.storefront import policies


class SectionType(StrEnum):
    """The closed set of registered section types (append-only)."""

    HERO = "hero"
    MENU = "menu"
    STORY = "story"
    CONTACT = "contact"
    GALLERY = "gallery"
    HOURS = "hours"


class HeroAction(StrEnum):
    """The hero's primary call to action — a closed enum, not free text.

    ``view_menu`` is ordinary in-site navigation to the menu.
    ``order_online`` is the M6 member this enum always reserved (M6B,
    ADR-026): stored content stays a *choice*, and the renderer gates it
    on the live ``ordering_enabled`` fact at render time — entitlement is
    a platform fact that changes independently of published content, so
    a hero authored with the ordering action degrades to the plain menu
    link whenever ordering is off (the D12 render-time-gate ruling).
    """

    NONE = "none"
    VIEW_MENU = "view_menu"
    ORDER_ONLINE = "order_online"


def _line(max_length: int) -> Callable[[object], object]:
    """Required single-line copy: normalized, bounded, control-free."""

    def _validate(value: object) -> object:
        if not isinstance(value, str):
            return value
        if policies.has_control_characters(value):
            msg = "must not contain control characters"
            raise ValueError(msg)
        text = policies.normalize_line(value)
        if not text:
            msg = "must not be blank"
            raise ValueError(msg)
        if len(text) > max_length:
            msg = f"must be at most {max_length} characters"
            raise ValueError(msg)
        return text

    return _validate


def _optional_line(max_length: int) -> Callable[[object], object]:
    """Optional single-line copy; blank normalizes to absent."""
    required = _line(max_length)

    def _validate(value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        if policies.has_control_characters(value):
            msg = "must not contain control characters"
            raise ValueError(msg)
        if not policies.normalize_line(value):
            return None
        return required(value)

    return _validate


def _block(max_length: int) -> Callable[[object], object]:
    """Required multi-line copy: paragraphs preserved, bounded, control-free."""

    def _validate(value: object) -> object:
        if not isinstance(value, str):
            return value
        if policies.has_control_characters(value, allow_newline=True):
            msg = "must not contain control characters"
            raise ValueError(msg)
        text = policies.normalize_block(value)
        if not text:
            msg = "must not be blank"
            raise ValueError(msg)
        if len(text) > max_length:
            msg = f"must be at most {max_length} characters"
            raise ValueError(msg)
        return text

    return _validate


def _section_id(value: object) -> object:
    """A stable structural key: lowercase slug, matched in full.

    ``re.fullmatch`` rather than a Pydantic ``pattern``: an anchored ``$``
    also matches before a trailing newline in some engines, which would let
    ``"hero-main\\n"`` through as a section id.
    """
    if not isinstance(value, str):
        return value
    if len(value) > policies.MAX_SECTION_ID_LENGTH:
        msg = f"must be at most {policies.MAX_SECTION_ID_LENGTH} characters"
        raise ValueError(msg)
    if re.fullmatch(policies.SECTION_ID_PATTERN, value) is None:
        msg = "must be a lowercase slug of letters, digits, and internal hyphens"
        raise ValueError(msg)
    return value


Heading = Annotated[str, BeforeValidator(_line(policies.MAX_HEADING_LENGTH))]
OptionalHeading = Annotated[
    str | None, BeforeValidator(_optional_line(policies.MAX_HEADING_LENGTH))
]
Subheading = Annotated[str | None, BeforeValidator(_optional_line(policies.MAX_SUBHEADING_LENGTH))]
Intro = Annotated[str | None, BeforeValidator(_optional_line(policies.MAX_INTRO_LENGTH))]
Body = Annotated[str, BeforeValidator(_block(policies.MAX_BODY_LENGTH))]
AddressLine = Annotated[str, BeforeValidator(_line(policies.MAX_ADDRESS_LINE_LENGTH))]
Phone = Annotated[str | None, BeforeValidator(_optional_line(policies.MAX_PHONE_LENGTH))]
Email = Annotated[str | None, BeforeValidator(_optional_line(policies.MAX_EMAIL_LENGTH))]
AltText = Annotated[str | None, BeforeValidator(_optional_line(policies.MAX_IMAGE_ALT_LENGTH))]
SectionId = Annotated[str, BeforeValidator(_section_id)]


class StorefrontModel(BaseModel):
    """Base for every composition model: strict, immutable, deterministic.

    ``extra="forbid"`` is the registry's teeth — an unknown property is a
    422, never a silently stored blob that a later renderer might trust.
    ``frozen=True`` keeps a validated configuration from being mutated in
    place after the fact.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class SectionImage(StorefrontModel):
    """One image reference: an opaque media asset id plus contextual alt text.

    ``alt_text`` belongs to *this* placement, not to the asset — the same
    contextual-alt contract catalog uses for item images (ADR-017 R2).
    Same-business ownership and public-delivery eligibility are database
    questions answered by the M4B service, not here.
    """

    media_id: uuid.UUID
    alt_text: AltText = None


class HeroProps(StorefrontModel):
    """Opening section: headline, optional supporting line, optional image."""

    heading: Heading
    subheading: Subheading = None
    image: SectionImage | None = None
    primary_action: HeroAction = HeroAction.NONE


class MenuProps(StorefrontModel):
    """Menu section: heading and optional introduction.

    Carries **no** item selection. Which items appear, in what order, and
    which are featured is already catalog's answer through the public menu
    projection (``featured_item_ids``, the centralized featured policy).
    A second selection here would be a competing source of truth.
    """

    heading: Heading
    intro: Intro = None


class StoryProps(StorefrontModel):
    """The restaurant's story: heading plus multi-paragraph plain text."""

    heading: Heading
    body: Body


class ContactProps(StorefrontModel):
    """Contact details as structured fields.

    Deliberately no hours field of any kind — structured weekly hours,
    exceptions, and "next opening" are M5's domain, and a free-text
    opening-times line here would be the freeform storefront text docs/03
    rules out. ``email`` is bounded plain text, not a deliverability
    guarantee.
    """

    heading: Heading
    address_lines: list[AddressLine] = Field(
        default_factory=list, max_length=policies.MAX_ADDRESS_LINES
    )
    phone: Phone = None
    email: Email = None


class HoursProps(StorefrontModel):
    """Hours section: presentation choices only, never schedule data (D5).

    Follows ``MenuProps`` to the letter: the section says *how* the hours
    are introduced — heading, optional intro, and whether the live
    open/closed status line is shown — while the weekly schedule,
    exceptions, and instant facts are the hours domain's answer through
    the public availability projection, composed at render time. A
    schedule field here would be a second source of truth that publication
    would freeze into immutable version history (ADR-025 D5).
    """

    heading: Heading
    intro: Intro = None
    show_open_now: bool = True


class GalleryProps(StorefrontModel):
    """A bounded set of images, in display order."""

    heading: OptionalHeading = None
    images: list[SectionImage] = Field(default_factory=list, max_length=policies.MAX_GALLERY_IMAGES)

    @field_validator("images", mode="after")
    @classmethod
    def _distinct_assets(cls, images: list[SectionImage]) -> list[SectionImage]:
        seen = {image.media_id for image in images}
        if len(seen) != len(images):
            msg = "gallery images must reference distinct media assets"
            raise ValueError(msg)
        return images


class SectionBase(StorefrontModel):
    """Fields every section carries, whatever its type."""

    id: SectionId
    enabled: bool = True


class HeroSection(SectionBase):
    type: Literal[SectionType.HERO]
    props: HeroProps


class MenuSection(SectionBase):
    type: Literal[SectionType.MENU]
    props: MenuProps


class StorySection(SectionBase):
    type: Literal[SectionType.STORY]
    props: StoryProps


class ContactSection(SectionBase):
    type: Literal[SectionType.CONTACT]
    props: ContactProps


class GallerySection(SectionBase):
    type: Literal[SectionType.GALLERY]
    props: GalleryProps


class HoursSection(SectionBase):
    type: Literal[SectionType.HOURS]
    props: HoursProps


# The concrete union (every registered section model) and the discriminated
# form used as a field annotation. Both exist because the plain union is
# what type annotations elsewhere need — ``Annotated`` cannot be used as a
# parameter type without dragging the discriminator into every signature.
AnySection = (
    HeroSection | MenuSection | StorySection | ContactSection | GallerySection | HoursSection
)

Section = Annotated[AnySection, Field(discriminator="type")]

# Every registered type must have a model in the union above. The identity
# is asserted by a permanent test, so registering a type without a model
# (or vice versa) fails rather than producing a section nothing can build.
SECTION_MODELS: dict[SectionType, type[AnySection]] = {
    SectionType.HERO: HeroSection,
    SectionType.MENU: MenuSection,
    SectionType.STORY: StorySection,
    SectionType.CONTACT: ContactSection,
    SectionType.GALLERY: GallerySection,
    SectionType.HOURS: HoursSection,
}


def referenced_media_ids(section: AnySection) -> list[uuid.UUID]:
    """Every media asset this section references, in stable order.

    One place that knows where images live inside the *section* registry, so
    the claim/validation path and any later reference audit cannot disagree
    with the schemas. Adding an image-bearing field without extending this
    function is caught by a permanent test.

    The document-level answer is ``composition.referenced_media_ids``, which
    walks the theme as well and delegates here for each section (M4G-A):
    ``theme.logo`` is not a section, so this function alone is no longer the
    complete picture.
    """
    if isinstance(section, HeroSection):
        return [section.props.image.media_id] if section.props.image is not None else []
    if isinstance(section, GallerySection):
        return [image.media_id for image in section.props.images]
    return []
