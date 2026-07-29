"""Public storefront projection schemas and pure assembly rules (M4C).

The database-backed behavior (resolution, publication lifecycle, media
descriptors, the delivery predicate) lives in
``tests/security/test_public_storefront.py``; this module covers what
needs no database — the non-disclosure contract of the public schemas and
the pure projection helpers.
"""

import uuid

from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.storefront import public_schemas, public_service
from app.domains.storefront.composition import parse_config
from app.domains.storefront.sections import HeroAction

# Fields that exist administratively (or in storage metadata) and must
# never appear on a public storefront schema. Denylist, not allowlist: it
# keeps failing as the public contract grows, which is exactly when an
# internal field is most likely to be added by reflex.
_DENIED_PUBLIC_FIELDS = {
    # Administrative version state (ADR-020 §3-§4).
    "state",
    "version_number",
    "lock_version",
    "schema_version",
    "source_version_id",
    "published_at",
    "published_by_user_id",
    "created_at",
    "updated_at",
    "business_id",
    "version_id",
    "config",
    # Presentation bookkeeping: everything projected is enabled.
    "enabled",
    "position",
    # Media internals (ADR-017 R3): identifiers, keys, checksums.
    "media_id",
    "asset_id",
    "key",
    "storage_key",
    "path",
    "checksum",
    "checksum_sha256",
    "original_filename",
    "declared_content_type",
    "source_format",
    "byte_size",
    "status",
    "pending_expires_at",
}

_PUBLIC_MODELS = (
    public_schemas.PublicStorefront,
    public_schemas.PublicTheme,
    public_schemas.PublicHeroSection,
    public_schemas.PublicMenuSection,
    public_schemas.PublicStorySection,
    public_schemas.PublicContactSection,
    public_schemas.PublicGallerySection,
    public_schemas.PublicHeroProps,
    public_schemas.PublicMenuSectionProps,
    public_schemas.PublicStoryProps,
    public_schemas.PublicContactProps,
    public_schemas.PublicGalleryProps,
    public_schemas.PublicStorefrontImage,
    public_schemas.PublicStorefrontImageVariant,
)


class TestPublicSchemasCarryNoInternalField:
    def test_no_public_schema_declares_a_denied_field(self) -> None:
        for model in _PUBLIC_MODELS:
            offending = set(model.model_fields) & _DENIED_PUBLIC_FIELDS
            assert offending == set(), f"{model.__name__} exposes {sorted(offending)}"

    def test_currency_is_only_reachable_through_the_business_summary(self) -> None:
        assert "currency" not in public_schemas.PublicStorefront.model_fields
        summary_field = public_schemas.PublicStorefront.model_fields["business"]
        assert summary_field.annotation is PublicSiteSummary
        assert "currency" in PublicSiteSummary.model_fields

    def test_every_registered_section_type_has_a_public_model(self) -> None:
        # The identity between the persisted registry and the public union,
        # so registering a section type without a public projection fails
        # here rather than at the first live request.
        from typing import get_args

        from app.domains.storefront.sections import SectionType

        public_types: set[object] = set()
        for model in (
            public_schemas.PublicHeroSection,
            public_schemas.PublicMenuSection,
            public_schemas.PublicStorySection,
            public_schemas.PublicContactSection,
            public_schemas.PublicGallerySection,
        ):
            annotation = model.model_fields["type"].annotation
            assert annotation is not None
            public_types.update(get_args(annotation))
        assert public_types == set(SectionType)


class TestEnabledSections:
    def _config(self) -> object:
        return parse_config(
            {
                "schema_version": 1,
                "theme": {"accent": "#a34b2a"},
                "sections": [
                    {
                        "id": "hero-main",
                        "type": "hero",
                        "enabled": True,
                        "props": {"heading": "Kept"},
                    },
                    {
                        "id": "story-main",
                        "type": "story",
                        "enabled": False,
                        "props": {"heading": "Story", "body": "Dropped"},
                    },
                ],
            }
        )

    def test_disabled_sections_are_filtered_in_order(self) -> None:
        config = self._config()
        sections = public_service.enabled_sections(config)  # type: ignore[arg-type]
        assert [section.id for section in sections] == ["hero-main"]


class TestSectionProjection:
    def test_hero_without_media_projects_copy_and_action(self) -> None:
        config = parse_config(
            {
                "schema_version": 1,
                "theme": {"accent": "#a34b2a"},
                "sections": [
                    {
                        "id": "hero-main",
                        "type": "hero",
                        "enabled": True,
                        "props": {
                            "heading": "Welcome",
                            "subheading": "Bailey Ave",
                            "primary_action": "view_menu",
                        },
                    }
                ],
            }
        )
        (section,) = config.sections
        view = public_service._section_view(
            section, {}, {}, public_service.preview_media_url_builder(uuid.uuid4())
        )
        assert isinstance(view, public_schemas.PublicHeroSection)
        assert view.props.heading == "Welcome"
        assert view.props.subheading == "Bailey Ave"
        assert view.props.primary_action is HeroAction.VIEW_MENU
        # An unresolvable reference is absent, never a dead URL.
        assert view.props.image is None

    def test_gallery_with_unresolvable_assets_projects_empty(self) -> None:
        config = parse_config(
            {
                "schema_version": 1,
                "theme": {"accent": "#a34b2a"},
                "sections": [
                    {
                        "id": "gallery-main",
                        "type": "gallery",
                        "enabled": True,
                        "props": {"images": [{"media_id": str(uuid.uuid4())}]},
                    }
                ],
            }
        )
        (section,) = config.sections
        view = public_service._section_view(
            section, {}, {}, public_service.preview_media_url_builder(uuid.uuid4())
        )
        assert isinstance(view, public_schemas.PublicGallerySection)
        assert view.props.images == []


class TestPreviewMediaUrlBuilder:
    def test_urls_address_the_authenticated_member_media_route(self) -> None:
        business_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        build = public_service.preview_media_url_builder(business_id)
        assert build(asset_id, "canonical") == (
            f"/api/v1/businesses/{business_id}/media/{asset_id}/file/canonical"
        )
        assert build(asset_id, "w320").startswith(f"/api/v1/businesses/{business_id}/media/")
