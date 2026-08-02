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
    public_schemas.PublicHoursSection,
    public_schemas.PublicHeroProps,
    public_schemas.PublicMenuSectionProps,
    public_schemas.PublicStoryProps,
    public_schemas.PublicContactProps,
    public_schemas.PublicGalleryProps,
    public_schemas.PublicHoursSectionProps,
    public_schemas.PublicStorefrontImage,
    public_schemas.PublicStorefrontImageVariant,
    public_schemas.PublicThemeLogo,
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
            public_schemas.PublicHoursSection,
        ):
            annotation = model.model_fields["type"].annotation
            assert annotation is not None
            public_types.update(get_args(annotation))
        assert public_types == set(SectionType)


class TestPublicThemeProjection:
    """The theme half of the projection (M4G-A, ADR-024 §4, §7, §10)."""

    def test_the_theme_projects_the_registry_tokens_and_the_logo_slot(self) -> None:
        assert set(public_schemas.PublicTheme.model_fields) == {
            "accent",
            "palette",
            "type_pairing",
            "logo",
        }

    def test_every_theme_field_is_required_in_the_projection(self) -> None:
        """A projection states everything; nothing is inferred by absence.

        `logo` is required-but-nullable, the `PublicHeroProps.image`
        precedent: a renderer reads `null` rather than having to distinguish
        "absent" from "not set".
        """
        for name, field in public_schemas.PublicTheme.model_fields.items():
            assert field.is_required(), name

    def test_the_projected_logo_carries_no_alt_text(self) -> None:
        """§7's decorative ruling on the output side.

        A null `alt_text` passed through by a renderer would produce an
        *unlabelled* image rather than a decorative one, so there is
        deliberately no value to pass: `alt=""` is the only thing a variant
        can write. The input-side counterpart is `ThemeLogo`.
        """
        assert "alt_text" not in public_schemas.PublicThemeLogo.model_fields
        assert "alt_text" in public_schemas.PublicStorefrontImage.model_fields

    def test_the_projected_logo_reserves_its_box(self) -> None:
        """Intrinsic dimensions travel with the logo, so the header never
        shifts while it loads (§7: no CLS)."""
        assert {"width", "height"} <= set(public_schemas.PublicThemeLogo.model_fields)


class TestPubliclyReferencedMediaIds:
    """The one collection shared by the projection and the §10 predicate."""

    @staticmethod
    def _config(*, logo: uuid.UUID | None, hero: uuid.UUID, gallery: uuid.UUID) -> object:
        theme: dict[str, object] = {"accent": "#a34b2a"}
        if logo is not None:
            theme["logo"] = {"media_id": str(logo)}
        return parse_config(
            {
                "schema_version": 1,
                "theme": theme,
                "sections": [
                    {
                        "id": "hero-main",
                        "type": "hero",
                        "enabled": True,
                        "props": {"heading": "Kept", "image": {"media_id": str(hero)}},
                    },
                    {
                        "id": "gallery",
                        "type": "gallery",
                        "enabled": False,
                        "props": {"images": [{"media_id": str(gallery)}]},
                    },
                ],
            }
        )

    def test_the_theme_logo_precedes_enabled_section_media(self) -> None:
        logo, hero, gallery = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        config = self._config(logo=logo, hero=hero, gallery=gallery)
        collected = public_service.publicly_referenced_media_ids(config)  # type: ignore[arg-type]
        assert collected == [logo, hero]

    def test_a_disabled_sections_media_is_excluded(self) -> None:
        """Least exposure, unchanged by M4G (ruling R-5): a disabled section
        is omitted from the projection, so its media has no current public
        rendering purpose."""
        logo, hero, gallery = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        config = self._config(logo=logo, hero=hero, gallery=gallery)
        assert gallery not in public_service.publicly_referenced_media_ids(config)  # type: ignore[arg-type]

    def test_the_logo_is_independent_of_section_enablement(self) -> None:
        """A logo is chrome, not a section, so disabling every section never
        withdraws it — the third leg is genuinely independent (§7)."""
        logo = uuid.uuid4()
        config = parse_config(
            {
                "schema_version": 1,
                "theme": {"logo": {"media_id": str(logo)}},
                "sections": [
                    {
                        "id": "hero-main",
                        "type": "hero",
                        "enabled": False,
                        "props": {"heading": "Hidden"},
                    }
                ],
            }
        )
        assert public_service.enabled_sections(config) == []
        assert public_service.publicly_referenced_media_ids(config) == [logo]

    def test_no_logo_means_no_theme_contribution(self) -> None:
        hero, gallery = uuid.uuid4(), uuid.uuid4()
        config = self._config(logo=None, hero=hero, gallery=gallery)
        assert public_service.publicly_referenced_media_ids(config) == [hero]  # type: ignore[arg-type]


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

    def test_hours_projects_presentation_choices_and_no_schedule(self) -> None:
        """The D5 seam on the read side: the projection carries the owner's
        presentation choices verbatim and no hours data of any shape — the
        schedule is the availability projection's answer, composed at
        render time by the storefront application."""
        config = parse_config(
            {
                "schema_version": 1,
                "theme": {"accent": "#a34b2a"},
                "sections": [
                    {
                        "id": "hours",
                        "type": "hours",
                        "enabled": True,
                        "props": {"heading": "Opening hours", "show_open_now": False},
                    }
                ],
            }
        )
        (section,) = config.sections
        view = public_service._section_view(
            section, {}, {}, public_service.preview_media_url_builder(uuid.uuid4())
        )
        assert isinstance(view, public_schemas.PublicHoursSection)
        assert view.props.heading == "Opening hours"
        assert view.props.intro is None
        assert view.props.show_open_now is False
        assert set(public_schemas.PublicHoursSectionProps.model_fields) == {
            "heading",
            "intro",
            "show_open_now",
        }

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
