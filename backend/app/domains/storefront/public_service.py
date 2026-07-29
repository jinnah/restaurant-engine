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
predicate (ADR-020 §10, ruling R-5): an asset is deliverable through the
storefront branch only while an **enabled** section of the currently
published version references it. Disabled sections are omitted from the
public projection, so their media has no current public rendering purpose
and authorizes nothing — least exposure. The application-layer media
router composes this predicate with catalog's, so neither domain imports
the other.

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
from app.domains.storefront.composition import StorefrontConfig, parse_config
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
        variants=[
            PublicStorefrontImageVariant(
                variant=variant.variant,  # type: ignore[arg-type]
                width=variant.width,
                height=variant.height,
                url=url_builder(asset.id, variant.variant),
            )
            for variant in variants
        ],
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
    referenced = list(
        dict.fromkeys(
            media_id for section in sections for media_id in referenced_media_ids(section)
        )
    )
    assets, variants_by_asset = media_public.list_public_representations(
        db,
        business_id=business_id,
        asset_ids=referenced,
        include_pending=include_pending_media,
    )
    return PublicStorefront(
        business=summary,
        design_variant=variant,
        theme=PublicTheme(accent=config.theme.accent),
        sections=[
            _section_view(section, assets, variants_by_asset, url_builder) for section in sections
        ],
    )


def media_is_publicly_referenced(
    db: Session, *, business_id: uuid.UUID, media_id: uuid.UUID
) -> bool:
    """Is this asset referenced by an enabled published storefront section?

    The storefront half of the public media-delivery predicate (ADR-020
    §10, ruling R-5). It reads exactly the one ``state='published'`` row
    of the already-resolved Business, so draft-only, archived-only,
    unpublished, and cross-business references structurally authorize
    nothing; a disabled section's reference authorizes nothing either,
    because it is omitted from the public projection and has no current
    rendering purpose.

    Fail-closed to **deny** (ruling R-6): a published row whose stored
    config or variant no longer validates is an integrity defect — it is
    logged as an anomaly and authorizes nothing, so corruption can never
    become anonymous media access, and the anonymous route keeps its
    neutral 404 rather than surfacing a 500.
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
    return any(media_id in referenced_media_ids(section) for section in enabled_sections(config))
