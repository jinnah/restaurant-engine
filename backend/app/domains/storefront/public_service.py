"""Public storefront projection and preview assembly (M4C, ADR-020).

The read side of storefront composition. Two consumers share one
assembler, differing only in which version row they read and which media
URL builder they inject (ADR-020 §9):

* the **public projection** reads the currently published row of the
  Host-resolved Business and addresses images through the anonymous
  public media route;
* the **authenticated preview** reads the current draft and addresses
  images through the member media route, which already serves pending
  assets with ``no-store``.

This module also owns the storefront half of the public media-delivery
predicate (ADR-020 §10, ruling R-5, amended 2026-07-30 by ADR-024 §7): an
asset is deliverable through the storefront branch while an **enabled**
section of the currently published version references it, **or that
version's theme does**. Disabled sections are omitted from the public
projection, so their media has no current public rendering purpose and
authorizes nothing — least exposure; the theme carries no enablement, so a
published logo is authorized independently of section state. The
application-layer media router composes this predicate with catalog's, so
neither domain imports the other.

Fail-closed behavior splits by question (approved ruling R-6): the
*projection* of a corrupt stored config or unregistered variant is an
integrity defect and propagates to the opaque 500 boundary (the M4B
completion-1 rule for read projections); the *authorization predicate*
over the same corruption fails closed to "authorizes nothing" — a neutral
404, never access, never a 500 on the anonymous media route. Both paths
log a bounded anomaly (business id and reason only; never config content).
"""

import uuid
from collections.abc import Callable

import structlog
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.media import public_service as media_public
from app.domains.media.models import MediaAsset, MediaAssetVariant
from app.domains.storefront import repository
from app.domains.storefront.composition import (
    StorefrontConfig,
    parse_config,
    theme_media_ids,
)
from app.domains.storefront.models import StorefrontVersion
from app.domains.storefront.public_schemas import (
    AnyPublicSection,
    PublicContactProps,
    PublicContactSection,
    PublicGalleryProps,
    PublicGallerySection,
    PublicHeroProps,
    PublicHeroSection,
    PublicMenuSection,
    PublicMenuSectionProps,
    PublicStorefront,
    PublicStorefrontImage,
    PublicStorefrontImageVariant,
    PublicStoryProps,
    PublicStorySection,
    PublicTheme,
    PublicThemeLogo,
)
from app.domains.storefront.sections import (
    AnySection,
    ContactSection,
    GallerySection,
    HeroSection,
    MenuSection,
    SectionImage,
    StorySection,
    referenced_media_ids,
)
from app.domains.storefront.variants import DesignVariant

_LOGGER_NAME = "app.storefront.public"

# Builds the delivery URL for one (asset id, logical variant) pair. The
# public assembler injects the anonymous media URL; the preview injects
# the authenticated member route. Nothing below knows which.
MediaUrlBuilder = Callable[[uuid.UUID, str], str]


def preview_media_url_builder(business_id: uuid.UUID) -> MediaUrlBuilder:
    """URLs addressing the authenticated member media route (ADR-020 §10).

    The one existing surface that serves pending draft media — no new
    media delivery surface is created for preview, and no public URL is
    ever advertised for a pending asset.
    """

    def _build(asset_id: uuid.UUID, variant: str) -> str:
        return f"/api/v1/businesses/{business_id}/media/{asset_id}/file/{variant}"

    return _build


def warn_config_invalid(business_id: uuid.UUID, context: str) -> None:
    """Record a bounded integrity anomaly — ids and reason, never content.

    Resolved per call rather than cached at import (the media public
    logging precedent): this fires only on genuine integrity defects.
    """
    structlog.get_logger(_LOGGER_NAME).warning(
        "storefront_published_config_invalid",
        business_id=str(business_id),
        context=context,
    )


def _variant_views(
    asset: MediaAsset,
    variants: list[MediaAssetVariant],
    url_builder: MediaUrlBuilder,
) -> list[PublicStorefrontImageVariant]:
    """The responsive rendition descriptors of one asset, in stored order.

    Shared by the section-image and theme-logo views so the two descriptor
    families cannot drift in URL construction or dimension reporting.
    """
    return [
        PublicStorefrontImageVariant(
            variant=variant.variant,  # type: ignore[arg-type]
            width=variant.width,
            height=variant.height,
            url=url_builder(asset.id, variant.variant),
        )
        for variant in variants
    ]


def _image_view(
    image: SectionImage,
    asset: MediaAsset,
    variants: list[MediaAssetVariant],
    url_builder: MediaUrlBuilder,
) -> PublicStorefrontImage:
    """Describe one resolved image by URL and true pixel dimensions.

    The alt text belongs to the *placement* (the section's reference), not
    the asset — the contextual-alt contract (ADR-017 R2).
    """
    return PublicStorefrontImage(
        alt_text=image.alt_text,
        width=asset.width,
        height=asset.height,
        url=url_builder(asset.id, media_public.CANONICAL_VARIANT),
        variants=_variant_views(asset, variants, url_builder),
    )


def _logo_view(
    asset: MediaAsset,
    variants: list[MediaAssetVariant],
    url_builder: MediaUrlBuilder,
) -> PublicThemeLogo:
    """Describe the resolved theme logo — the image view without alt text.

    The logo is permanently decorative (ADR-024 §7), so no alt text exists
    to project: the business name carries the meaning as text in every
    variant.
    """
    return PublicThemeLogo(
        width=asset.width,
        height=asset.height,
        url=url_builder(asset.id, media_public.CANONICAL_VARIANT),
        variants=_variant_views(asset, variants, url_builder),
    )


def _resolve_image(
    image: SectionImage | None,
    assets: dict[uuid.UUID, MediaAsset],
    variants_by_asset: dict[uuid.UUID, list[MediaAssetVariant]],
    url_builder: MediaUrlBuilder,
) -> PublicStorefrontImage | None:
    """One reference to a descriptor, or ``None`` when it cannot render.

    A reference whose asset is missing or not renderable degrades to no
    image rather than advertising a dead URL (ADR-020 §10: degradation
    removes a reference and can never grant access).
    """
    if image is None:
        return None
    asset = assets.get(image.media_id)
    if asset is None:
        return None
    return _image_view(image, asset, variants_by_asset.get(asset.id, []), url_builder)


def _resolve_logo(
    config: StorefrontConfig,
    assets: dict[uuid.UUID, MediaAsset],
    variants_by_asset: dict[uuid.UUID, list[MediaAssetVariant]],
    url_builder: MediaUrlBuilder,
) -> PublicThemeLogo | None:
    """The theme logo descriptor, or ``None`` when it cannot render.

    Same degradation rule as a section image, and §7 makes it explicitly
    safe here: an unresolvable logo costs nothing informational, because the
    business name is always present as text and the image conveys nothing on
    its own.
    """
    logo = config.theme.logo
    if logo is None:
        return None
    asset = assets.get(logo.media_id)
    if asset is None:
        return None
    return _logo_view(asset, variants_by_asset.get(asset.id, []), url_builder)


def _section_view(
    section: AnySection,
    assets: dict[uuid.UUID, MediaAsset],
    variants_by_asset: dict[uuid.UUID, list[MediaAssetVariant]],
    url_builder: MediaUrlBuilder,
) -> AnyPublicSection:
    """Project one enabled section, resolving its media references."""
    if isinstance(section, HeroSection):
        return PublicHeroSection(
            id=section.id,
            type=section.type,
            props=PublicHeroProps(
                heading=section.props.heading,
                subheading=section.props.subheading,
                image=_resolve_image(section.props.image, assets, variants_by_asset, url_builder),
                primary_action=section.props.primary_action,
            ),
        )
    if isinstance(section, MenuSection):
        return PublicMenuSection(
            id=section.id,
            type=section.type,
            props=PublicMenuSectionProps(heading=section.props.heading, intro=section.props.intro),
        )
    if isinstance(section, StorySection):
        return PublicStorySection(
            id=section.id,
            type=section.type,
            props=PublicStoryProps(heading=section.props.heading, body=section.props.body),
        )
    if isinstance(section, ContactSection):
        return PublicContactSection(
            id=section.id,
            type=section.type,
            props=PublicContactProps(
                heading=section.props.heading,
                address_lines=list(section.props.address_lines),
                phone=section.props.phone,
                email=section.props.email,
            ),
        )
    assert isinstance(section, GallerySection)  # noqa: S101 - closed registry union
    resolved = [
        view
        for image in section.props.images
        if (view := _resolve_image(image, assets, variants_by_asset, url_builder)) is not None
    ]
    return PublicGallerySection(
        id=section.id,
        type=section.type,
        props=PublicGalleryProps(heading=section.props.heading, images=resolved),
    )


def enabled_sections(config: StorefrontConfig) -> list[AnySection]:
    """The sections a public rendering presents, in display order.

    One definition of "publicly present" shared by the projection and the
    media predicate, so what renders and what authorizes cannot drift
    (ruling R-5).
    """
    return [section for section in config.sections if section.enabled]


def publicly_referenced_media_ids(config: StorefrontConfig) -> list[uuid.UUID]:
    """Every media asset a public rendering of this configuration presents.

    The theme first, then the **enabled** sections in display order. Like
    :func:`enabled_sections`, this is one definition shared by the
    projection and the ADR-020 §10 predicate, so an asset the public page
    shows and an asset the public media route authorizes are the same set by
    construction (ruling R-5, extended to the theme by ADR-024 §7).

    Two boundaries are deliberate. A **disabled** section's media is
    excluded: it is omitted from the projection, so it has no current public
    rendering purpose and authorizes nothing — least exposure. The **theme**
    has no enablement flag — a logo is chrome, not a section — so a set logo
    is always present here, independently of how many sections are enabled.
    """
    ids = theme_media_ids(config.theme)
    for section in enabled_sections(config):
        ids.extend(referenced_media_ids(section))
    return ids


def assemble_storefront(
    db: Session,
    *,
    business_id: uuid.UUID,
    summary: PublicSiteSummary,
    row: StorefrontVersion,
    url_builder: MediaUrlBuilder,
    include_pending_media: bool = False,
) -> PublicStorefront:
    """Project one version row into the render-facing representation.

    Fail-closed: a stored config or variant the code-owned registries no
    longer accept cannot arise through any application path, so a parse
    failure here is an integrity defect and propagates to the opaque
    internal-error boundary (M4B completion 1) — never rendered as if
    valid. Callers on the public surface log the anomaly before letting it
    propagate.

    Media descriptors are built only for references whose assets the
    database confirms renderable *now* (active — plus pending for the
    authenticated preview); anything else degrades to an image-less
    presentation rather than advertising a URL that would answer 404.
    """
    config = parse_config(row.config)
    variant = DesignVariant(row.design_variant)
    sections = enabled_sections(config)
    referenced = list(dict.fromkeys(publicly_referenced_media_ids(config)))
    assets, variants_by_asset = media_public.list_public_representations(
        db,
        business_id=business_id,
        asset_ids=referenced,
        include_pending=include_pending_media,
    )
    return PublicStorefront(
        business=summary,
        design_variant=variant,
        theme=PublicTheme(
            accent=config.theme.accent,
            palette=config.theme.palette,
            type_pairing=config.theme.type_pairing,
            logo=_resolve_logo(config, assets, variants_by_asset, url_builder),
        ),
        sections=[
            _section_view(section, assets, variants_by_asset, url_builder) for section in sections
        ],
    )


def media_is_publicly_referenced(
    db: Session, *, business_id: uuid.UUID, media_id: uuid.UUID
) -> bool:
    """Is this asset presented by the currently published storefront?

    The storefront half of the public media-delivery predicate (ADR-020
    §10, ruling R-5, as amended 2026-07-30 by ADR-024 §7). It reads exactly
    the one ``state='published'`` row of the already-resolved Business, so
    draft-only, archived-only, superseded, unpublished, and cross-business
    references structurally authorize nothing; a disabled section's
    reference authorizes nothing either, because it is omitted from the
    public projection and has no current rendering purpose.

    The amended predicate has **three independent legs**, and this function
    owns the second and third: an enabled section of the current published
    version, **or that version's theme**. The theme leg is genuinely
    independent — a logo is chrome rather than a section, so it is
    authorized even when every section is disabled, and disabling sections
    never withdraws it. The catalog leg is composed by the media router,
    so neither domain imports the other.

    Fail-closed to **deny** (ruling R-6): a published row whose stored
    config or variant no longer validates is an integrity defect — it is
    logged as an anomaly and authorizes nothing, so corruption can never
    become anonymous media access, and the anonymous route keeps its
    neutral 404 rather than surfacing a 500. An unregistered stored palette
    or pairing fails here exactly as an unregistered variant does.
    """
    row = repository.get_published(db, business_id=business_id)
    if row is None:
        return False
    try:
        config = parse_config(row.config)
        DesignVariant(row.design_variant)
    except (ValidationError, ValueError):
        warn_config_invalid(business_id, "media_predicate")
        return False
    return media_id in publicly_referenced_media_ids(config)
