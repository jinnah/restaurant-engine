"""Section registry and composition contract (M4A, ADR-020).

Pure tests: the registry is Pydantic and needs no database. They pin the
rules an M4B service, an M4D renderer, and any future section type all
depend on — including the ones whose absence is the decision (no hours, no
ordering action, no rich text).
"""

import uuid
from typing import get_args

import pytest
from pydantic import ValidationError

from app.domains.catalog import policies as catalog_policies
from app.domains.media import policies as media_policies
from app.domains.storefront import composition, policies, sections, theme_registries
from app.domains.storefront.composition import (
    default_config,
    dump_config,
    parse_config,
)
from app.domains.storefront.sections import HeroAction, SectionType

# Bengali written as escapes on purpose: composed and decomposed forms are
# visually identical, so literal text would make these tests look like they
# compare a string to itself. U+09CB (BENGALI VOWEL SIGN O) canonically
# decomposes to U+09C7 + U+09BE - two spellings of one grapheme, which is
# exactly what NFC normalization has to reconcile.
_BENGALI_COMPOSED = "কো"
_BENGALI_DECOMPOSED = "কো"
# A realistic, NFC-stable Bengali word ("Bangla").
_BENGALI_WORD = "বাংলা"


def _hero(**props: object) -> dict[str, object]:
    return {
        "id": "hero-main",
        "type": "hero",
        "enabled": True,
        "props": {"heading": "Welcome", **props},
    }


def _config(*section_dicts: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "theme": {"accent": "#a34b2a"},
        "sections": list(section_dicts),
    }


# --- The five registered types ------------------------------------------------


def test_every_registered_type_has_a_model_and_builds() -> None:
    """Registry completeness: a declared type must be constructible.

    The guard against registering a ``SectionType`` whose model nobody
    wrote — which would be a configuration the API advertises and the
    validator rejects.
    """
    assert set(sections.SECTION_MODELS) == set(SectionType)
    for section_type, model in sections.SECTION_MODELS.items():
        # The discriminator literal and the registry key are the same value.
        assert get_args(model.model_fields["type"].annotation) == (section_type,)


def test_hero_section_accepts_its_full_shape() -> None:
    media_id = uuid.uuid4()
    config = parse_config(
        _config(
            _hero(
                subheading="Bengali home cooking in Buffalo",
                image={"media_id": str(media_id), "alt_text": "The dining room"},
                primary_action="view_menu",
            )
        )
    )

    hero = config.sections[0]
    assert isinstance(hero, sections.HeroSection)
    assert hero.props.primary_action is HeroAction.VIEW_MENU
    assert hero.props.image is not None
    assert hero.props.image.media_id == media_id


def test_menu_story_contact_and_gallery_accept_their_shapes() -> None:
    config = parse_config(
        _config(
            {"id": "menu", "type": "menu", "props": {"heading": "Menu", "intro": "Cooked daily."}},
            {"id": "story", "type": "story", "props": {"heading": "Our story", "body": "A\n\nB"}},
            {
                "id": "contact",
                "type": "contact",
                "props": {
                    "heading": "Find us",
                    "address_lines": ["12 Main St", "Buffalo, NY"],
                    "phone": "+1 716 555 0100",
                    "email": "hello@example.com",
                },
            },
            {
                "id": "gallery",
                "type": "gallery",
                "props": {"images": [{"media_id": str(uuid.uuid4())}]},
            },
        )
    )

    assert [section.type for section in config.sections] == [
        SectionType.MENU,
        SectionType.STORY,
        SectionType.CONTACT,
        SectionType.GALLERY,
    ]
    story = config.sections[1]
    assert isinstance(story, sections.StorySection)
    # Paragraph breaks survive; the block normalizer is not a line collapser.
    assert story.props.body == "A\n\nB"


def test_enabled_defaults_to_true_and_array_order_is_the_contract() -> None:
    config = parse_config(
        _config(
            {"id": "menu", "type": "menu", "props": {"heading": "Menu"}},
            _hero(),
        )
    )

    assert [section.id for section in config.sections] == ["menu", "hero-main"]
    assert all(section.enabled for section in config.sections)
    # No position field is exposed anywhere: order *is* the contract.
    assert "position" not in dump_config(config)["sections"][0]


# --- What the registry must refuse -------------------------------------------


def test_unknown_section_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_config(_config({"id": "x", "type": "testimonials", "props": {}}))


def test_unknown_property_is_rejected_not_ignored() -> None:
    """``extra="forbid"`` is the registry's teeth (ADR-020).

    A silently stored unknown key is a field a future renderer might trust.
    """
    with pytest.raises(ValidationError):
        parse_config(_config(_hero(tagline="smuggled")))
    with pytest.raises(ValidationError):
        parse_config(_config({**_hero(), "unexpected": 1}))
    with pytest.raises(ValidationError):
        parse_config({**_config(), "extra_root_key": True})


def test_no_section_may_carry_hours_or_open_now() -> None:
    """Structured hours belong to the hours domain, never to a section.

    M5D registered the ``hours`` section, but the D5 ruling stands: a
    free-text opening line on *any* section — including the hours section
    itself — would be the freeform storefront text docs/03 forbids and a
    second source of truth beside the availability projection.
    """
    for field in ("hours", "opening_hours", "open_now", "hours_text"):
        with pytest.raises(ValidationError):
            parse_config(
                _config(
                    {
                        "id": "contact",
                        "type": "contact",
                        "props": {"heading": "Find us", field: "Mon-Fri 9-5"},
                    }
                )
            )
    contact_fields = set(sections.ContactProps.model_fields)
    assert not {name for name in contact_fields if "hour" in name or "open" in name}


def test_hours_section_accepts_its_shape_and_defaults() -> None:
    """The M5D section (ADR-025 D5): heading, optional intro, one toggle."""
    config = parse_config(
        _config(
            {
                "id": "hours",
                "type": "hours",
                "props": {"heading": "Opening hours", "intro": "Kitchen closes 30 min early."},
            }
        )
    )
    hours = config.sections[0]
    assert isinstance(hours, sections.HoursSection)
    assert hours.props.heading == "Opening hours"
    assert hours.props.intro == "Kitchen closes 30 min early."
    # The status line defaults to shown; hiding it is the owner's choice.
    assert hours.props.show_open_now is True

    minimal = parse_config(_config({"id": "hours", "type": "hours", "props": {"heading": "Hours"}}))
    minimal_hours = minimal.sections[0]
    assert isinstance(minimal_hours, sections.HoursSection)
    assert minimal_hours.props.intro is None


def test_hours_section_is_data_free() -> None:
    """Ruling D5, made structural: presentation choices and nothing else.

    The section stores no schedule in any shape — no intervals, dates,
    minutes, timezone, or free-text hours line. The exact field set is
    pinned so a data-bearing field cannot arrive without failing here,
    and every smuggling attempt is a 422 through ``extra="forbid"``.
    """
    assert set(sections.HoursProps.model_fields) == {"heading", "intro", "show_open_now"}
    for field, value in (
        ("weekly", [{"day_of_week": 0, "opens_minute": 540, "closes_minute": 1020}]),
        ("intervals", []),
        ("timezone", "America/New_York"),
        ("hours_text", "Mon-Fri 9-5"),
        ("opens_minute", 540),
        ("is_open_now", True),
    ):
        with pytest.raises(ValidationError):
            parse_config(
                _config(
                    {
                        "id": "hours",
                        "type": "hours",
                        "props": {"heading": "Hours", field: value},
                    }
                )
            )


def test_hours_section_references_no_media() -> None:
    config = parse_config(_config({"id": "hours", "type": "hours", "props": {"heading": "Hours"}}))
    assert sections.referenced_media_ids(config.sections[0]) == []


def test_hero_action_is_a_closed_enum_with_the_m6_ordering_member() -> None:
    """The M6 seam, filled exactly as reserved (M6B, ADR-026).

    ``order_online`` is a stored *choice*; the renderer gates it on the
    live ``ordering_enabled`` fact at render time (ruling D12), so
    content never freezes an entitlement. The enum stays closed:
    anything else remains a 422.
    """
    assert {action.value for action in HeroAction} == {"none", "view_menu", "order_online"}
    accepted = parse_config(_config(_hero(primary_action="order_online")))
    hero = accepted.sections[0]
    assert isinstance(hero, sections.HeroSection)
    assert hero.props.primary_action is HeroAction.ORDER_ONLINE
    for rejected in ("order", "checkout", "buy_now", "https://example.com"):
        with pytest.raises(ValidationError):
            parse_config(_config(_hero(primary_action=rejected)))


def test_no_section_type_is_an_ordering_or_campaign_surface() -> None:
    registered = {section_type.value for section_type in SectionType}
    assert registered == {"hero", "menu", "story", "contact", "gallery", "hours"}
    assert not registered & {"order", "ordering", "cart", "checkout", "campaign", "popup"}


def test_invalid_nested_structures_are_rejected() -> None:
    # props must be an object, not a scalar or list
    with pytest.raises(ValidationError):
        parse_config(_config({"id": "hero-main", "type": "hero", "props": "Welcome"}))
    # a nested image must be an object with a real uuid
    with pytest.raises(ValidationError):
        parse_config(_config(_hero(image={"media_id": "not-a-uuid"})))
    with pytest.raises(ValidationError):
        parse_config(_config(_hero(image=[])))
    # sections must be a list
    with pytest.raises(ValidationError):
        parse_config({"schema_version": 1, "theme": {}, "sections": {"id": "hero-main"}})


def test_section_ids_are_slugs_matched_in_full() -> None:
    for rejected in ("Hero Main", "hero_main", "-hero", "hero-", "héro", "hero-main\n", ""):
        with pytest.raises(ValidationError):
            parse_config(_config({**_hero(), "id": rejected}))


def test_duplicate_ids_and_duplicate_types_are_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_config(
            _config(
                {"id": "same", "type": "menu", "props": {"heading": "A"}},
                {"id": "same", "type": "story", "props": {"heading": "B", "body": "b"}},
            )
        )
    # At most one section per type — the anti-page-builder guard.
    with pytest.raises(ValidationError):
        parse_config(
            _config(
                {"id": "menu-one", "type": "menu", "props": {"heading": "A"}},
                {"id": "menu-two", "type": "menu", "props": {"heading": "B"}},
            )
        )


def test_gallery_rejects_duplicate_assets_and_enforces_its_bound() -> None:
    repeated = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        parse_config(
            _config(
                {
                    "id": "gallery",
                    "type": "gallery",
                    "props": {"images": [{"media_id": repeated}, {"media_id": repeated}]},
                }
            )
        )
    too_many = [{"media_id": str(uuid.uuid4())} for _ in range(policies.MAX_GALLERY_IMAGES + 1)]
    with pytest.raises(ValidationError):
        parse_config(_config({"id": "gallery", "type": "gallery", "props": {"images": too_many}}))


def test_copy_bounds_and_control_characters_are_enforced() -> None:
    with pytest.raises(ValidationError):
        parse_config(_config(_hero(heading="x" * (policies.MAX_HEADING_LENGTH + 1))))
    with pytest.raises(ValidationError):
        parse_config(_config(_hero(heading="   ")))
    # A control character is refused, never silently stripped.
    with pytest.raises(ValidationError):
        parse_config(_config(_hero(heading="Welcome\x07")))
    with pytest.raises(ValidationError):
        parse_config(
            _config({"id": "story", "type": "story", "props": {"heading": "H", "body": "a\x00b"}})
        )
    with pytest.raises(ValidationError):
        parse_config(
            _config(
                {
                    "id": "contact",
                    "type": "contact",
                    "props": {
                        "heading": "Find us",
                        "address_lines": ["a"] * (policies.MAX_ADDRESS_LINES + 1),
                    },
                }
            )
        )


def test_theme_accent_is_a_token_not_a_stylesheet() -> None:
    assert parse_config(_config()).theme.accent == "#a34b2a"
    # Canonicalized to lowercase, whitespace trimmed.
    assert parse_config({**_config(), "theme": {"accent": " #A34B2A "}}).theme.accent == "#a34b2a"
    for rejected in ("red", "#fff", "#a34b2aa", "a34b2a", "expression(alert(1))", "#a34b2z"):
        with pytest.raises(ValidationError):
            parse_config({**_config(), "theme": {"accent": rejected}})


# --- Theme extension (M4G-A, ADR-024 §4) --------------------------------------


def test_theme_defaults_reproduce_the_delivered_presentation() -> None:
    """The additive fields default to what every storefront renders today."""
    theme = composition.Theme()
    assert theme.accent == policies.DEFAULT_ACCENT
    assert theme.palette is theme_registries.PaletteId.WARM
    assert theme.type_pairing is theme_registries.TypePairingId.HUMANIST
    assert theme.logo is None


def test_a_configuration_stored_before_m4g_parses_to_the_defaults() -> None:
    """The whole compatibility argument for keeping ``schema_version`` at 1.

    ``extra="forbid"`` rejects unknown keys on submission, but *missing*
    keys parse to defaults — so a row written before M4G reads as
    warm/humanist/no-logo, which is exactly its current appearance. No
    migration, backfill, or adoption workflow exists because none is needed.
    """
    legacy = parse_config({"schema_version": 1, "theme": {"accent": "#123abc"}, "sections": []})
    assert legacy.theme.accent == "#123abc"
    assert legacy.theme.palette is theme_registries.PaletteId.WARM
    assert legacy.theme.type_pairing is theme_registries.TypePairingId.HUMANIST
    assert legacy.theme.logo is None

    # A configuration with no theme key at all behaves identically.
    absent = parse_config({"schema_version": 1, "sections": []})
    assert absent.theme == legacy.theme.model_copy(update={"accent": policies.DEFAULT_ACCENT})


def test_the_schema_version_is_unchanged_by_the_theme_extension() -> None:
    """Additive-with-defaults was chosen precisely to avoid a v2 (§4)."""
    assert composition.SCHEMA_VERSION == 1
    assert parse_config(_config()).schema_version == 1
    with pytest.raises(ValidationError):
        parse_config({**_config(), "schema_version": 2})


def test_registered_palettes_and_pairings_are_accepted() -> None:
    for palette in theme_registries.PaletteId:
        parsed = parse_config({**_config(), "theme": {"palette": palette.value}})
        assert parsed.theme.palette is palette
    for pairing in theme_registries.TypePairingId:
        parsed = parse_config({**_config(), "theme": {"type_pairing": pairing.value}})
        assert parsed.theme.type_pairing is pairing


def test_unknown_palettes_and_pairings_are_rejected() -> None:
    """Writes reject unregistered values; nothing is silently defaulted."""
    for rejected in ("", "WARM", "crimson", "warm ", "url(evil)"):
        with pytest.raises(ValidationError):
            parse_config({**_config(), "theme": {"palette": rejected}})
    for rejected in ("", "serif-display", "editorial_serif", "HUMANIST"):
        with pytest.raises(ValidationError):
            parse_config({**_config(), "theme": {"type_pairing": rejected}})


def test_an_unknown_theme_key_is_still_forbidden() -> None:
    """The registry keeps its teeth: additive does not mean permissive."""
    with pytest.raises(ValidationError):
        parse_config({**_config(), "theme": {"font_url": "https://example.test/f.woff2"}})


def test_the_logo_is_a_bare_media_reference_with_no_alt_text() -> None:
    """§7's decorative ruling, made structural rather than advisory.

    A logo sits beside the business name, which stays the visible semantic
    ``h1`` in every variant, so alt text would duplicate the accessible name
    for the same fact. Accepting an ``alt_text`` here would invite owners to
    write text the product then ignores — so the field does not exist, and
    submitting one is a 422 like any other unknown key.
    """
    assert "alt_text" not in composition.ThemeLogo.model_fields
    media_id = uuid.uuid4()
    parsed = parse_config({**_config(), "theme": {"logo": {"media_id": str(media_id)}}})
    assert parsed.theme.logo is not None
    assert parsed.theme.logo.media_id == media_id

    with pytest.raises(ValidationError):
        parse_config(
            {
                **_config(),
                "theme": {"logo": {"media_id": str(media_id), "alt_text": "Our logo"}},
            }
        )


def test_a_malformed_logo_reference_is_rejected() -> None:
    rejected: list[object] = [{}, {"media_id": "not-a-uuid"}, {"media_id": None}, "an-id", []]
    for candidate in rejected:
        with pytest.raises(ValidationError):
            parse_config({**_config(), "theme": {"logo": candidate}})


def test_the_canonical_dump_gains_the_new_keys_and_still_round_trips() -> None:
    """The composition contract is preserved: the dump simply grows (§4).

    Field order follows declaration order, so the stored bytes stay stable
    for comparison, hashing, and diffing — the property the exact-no-op
    suppression in the draft service depends on.
    """
    media_id = uuid.uuid4()
    config = parse_config(
        {
            **_config(),
            "theme": {
                "accent": "#123abc",
                "palette": "midnight",
                "type_pairing": "geometric",
                "logo": {"media_id": str(media_id)},
            },
        }
    )
    dumped = dump_config(config)
    assert dumped["theme"] == {
        "accent": "#123abc",
        "palette": "midnight",
        "type_pairing": "geometric",
        "logo": {"media_id": str(media_id)},
    }
    assert list(dumped["theme"]) == ["accent", "palette", "type_pairing", "logo"]
    # dump -> parse -> dump is byte-identical, with and without a logo.
    assert dump_config(parse_config(dumped)) == dumped
    without_logo = dump_config(parse_config(_config()))
    assert dump_config(parse_config(without_logo)) == without_logo


def test_markup_is_stored_as_literal_text_not_a_rich_text_field() -> None:
    """There is no HTML field; markup is inert text the renderer escapes."""
    raw = "<script>alert(1)</script>"
    config = parse_config(_config(_hero(heading=raw)))
    hero = config.sections[0]
    assert isinstance(hero, sections.HeroSection)
    assert hero.props.heading == raw


# --- Unicode and the launch market -------------------------------------------


def test_bengali_text_is_stored_nfc_normalized() -> None:
    """Decomposed and composed Bengali must not become two different values."""
    decomposed = parse_config(_config(_hero(heading=_BENGALI_DECOMPOSED)))
    composed = parse_config(_config(_hero(heading=_BENGALI_COMPOSED)))

    hero_decomposed = decomposed.sections[0]
    hero_composed = composed.sections[0]
    assert isinstance(hero_decomposed, sections.HeroSection)
    assert isinstance(hero_composed, sections.HeroSection)
    assert hero_decomposed.props.heading == _BENGALI_COMPOSED
    assert hero_decomposed.props.heading == hero_composed.props.heading


def test_bengali_copy_survives_a_full_round_trip() -> None:
    config = parse_config(
        _config(
            {
                "id": "story",
                "type": "story",
                "props": {"heading": _BENGALI_WORD, "body": f"{_BENGALI_WORD}\n\n{_BENGALI_WORD}"},
            }
        )
    )

    reparsed = parse_config(dump_config(config))
    assert dump_config(reparsed) == dump_config(config)
    story = reparsed.sections[0]
    assert isinstance(story, sections.StorySection)
    assert story.props.heading == _BENGALI_WORD


def test_length_bounds_count_normalized_code_points() -> None:
    """A decomposed sequence that composes shorter is measured composed."""
    heading = _BENGALI_DECOMPOSED * (policies.MAX_HEADING_LENGTH // 2)
    # 3 code points each before NFC, 2 after: rejected raw, accepted composed.
    assert len(heading) > policies.MAX_HEADING_LENGTH
    config = parse_config(_config(_hero(heading=heading)))
    hero = config.sections[0]
    assert isinstance(hero, sections.HeroSection)
    assert len(hero.props.heading) <= policies.MAX_HEADING_LENGTH


def test_whitespace_is_collapsed_and_blank_optionals_become_absent() -> None:
    config = parse_config(_config(_hero(heading="  Welcome   home  ", subheading="   ")))
    hero = config.sections[0]
    assert isinstance(hero, sections.HeroSection)
    assert hero.props.heading == "Welcome home"
    assert hero.props.subheading is None


# --- Determinism and defaults -------------------------------------------------


def test_serialization_is_deterministic_and_round_trips() -> None:
    raw = _config(
        _hero(image={"media_id": str(uuid.uuid4()), "alt_text": "Dining room"}),
        {"id": "menu", "type": "menu", "props": {"heading": "Menu"}},
    )

    first = dump_config(parse_config(raw))
    second = dump_config(parse_config(raw))
    assert first == second
    # Stable through a full storage round trip, and JSON-compatible.
    assert dump_config(parse_config(first)) == first
    assert list(first) == ["schema_version", "theme", "sections"]
    assert isinstance(first["sections"][0]["props"]["image"]["media_id"], str)


def test_default_config_is_valid_empty_and_carries_the_default_accent() -> None:
    config = default_config()

    assert config.schema_version == composition.SCHEMA_VERSION
    assert config.sections == []
    assert config.theme.accent == policies.DEFAULT_ACCENT
    # It must survive its own round trip, since it is what a first draft stores.
    assert parse_config(dump_config(config)) == config


def test_schema_version_is_explicit_and_closed() -> None:
    assert composition.SCHEMA_VERSION == 1
    with pytest.raises(ValidationError):
        parse_config({**_config(), "schema_version": 2})
    with pytest.raises(ValidationError):
        parse_config({**_config(), "schema_version": 0})


def test_configuration_is_immutable_once_validated() -> None:
    config = parse_config(_config(_hero()))
    with pytest.raises(ValidationError):
        config.sections = []


def test_section_count_is_bounded_by_the_registry() -> None:
    """The bound is derived, never a hand-maintained number.

    With at most one section per type the bound is unreachable in practice
    — it is defence in depth against an oversized document, and it must
    keep tracking the registry as types are added.
    """
    assert composition.MAX_SECTIONS == len(SectionType)


# --- Media references ---------------------------------------------------------


def test_referenced_media_ids_covers_every_image_bearing_field() -> None:
    """The one place that knows where images live inside the registry.

    An image-bearing field added without extending ``referenced_media_ids``
    would silently escape the M4B claim and validation path — so the two
    are compared here rather than trusted to stay in step.
    """
    hero_image, first, second = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    config = parse_config(
        _config(
            _hero(image={"media_id": str(hero_image)}),
            {
                "id": "gallery",
                "type": "gallery",
                "props": {"images": [{"media_id": str(first)}, {"media_id": str(second)}]},
            },
        )
    )

    collected = [
        media_id
        for section in config.sections
        for media_id in sections.referenced_media_ids(section)
    ]
    assert collected == [hero_image, first, second]

    # Every occurrence of a media reference in the dumped document is
    # accounted for, so no field can hide one from the claim path.
    dumped = dump_config(config)
    found = _media_ids_in(dumped)
    assert found == {str(hero_image), str(first), str(second)}


def test_document_level_collection_reaches_every_media_id_in_the_dump() -> None:
    """The completeness invariant, raised from sections to the document.

    M4A pinned the *section* walk, which by construction could not have
    caught ``theme.logo`` — a reference living outside every section. The
    invariant that actually protects the claim path is document-level: every
    ``media_id`` the canonical dump contains must be reachable by
    ``composition.referenced_media_ids``. An image-bearing field added
    anywhere in the registry, theme or section, now fails here.
    """
    logo, hero_image, first, second = (uuid.uuid4() for _ in range(4))
    raw = _config(
        _hero(image={"media_id": str(hero_image)}),
        {
            "id": "gallery",
            "type": "gallery",
            "props": {"images": [{"media_id": str(first)}, {"media_id": str(second)}]},
        },
    )
    raw["theme"] = {"accent": "#a34b2a", "logo": {"media_id": str(logo)}}
    config = parse_config(raw)

    # Document order: the theme precedes the sections, and sections follow
    # display order — the canonical field order, so a claim sequence is
    # reproducible rather than incidental.
    assert composition.referenced_media_ids(config) == [logo, hero_image, first, second]

    dumped = dump_config(config)
    assert _media_ids_in(dumped) == {
        str(media_id) for media_id in composition.referenced_media_ids(config)
    }


def test_theme_media_ids_is_empty_without_a_logo() -> None:
    config = parse_config(_config())
    assert composition.theme_media_ids(config.theme) == []
    assert composition.referenced_media_ids(config) == []


def test_document_collection_preserves_a_reference_shared_by_theme_and_section() -> None:
    """A faithful walk, not a set: callers de-duplicate explicitly.

    Nothing forbids a business using one asset as both its logo and its hero
    image, and the claim path's ``dict.fromkeys`` is what collapses them —
    collapsing here would hide a genuine second occurrence from the
    completeness invariant above.
    """
    shared = uuid.uuid4()
    raw = _config(_hero(image={"media_id": str(shared)}))
    raw["theme"] = {"logo": {"media_id": str(shared)}}
    config = parse_config(raw)
    assert composition.referenced_media_ids(config) == [shared, shared]
    assert list(dict.fromkeys(composition.referenced_media_ids(config))) == [shared]


def _media_ids_in(node: object) -> set[str]:
    if isinstance(node, dict):
        found: set[str] = set()
        for key, value in node.items():
            if key == "media_id" and isinstance(value, str):
                found.add(value)
            else:
                found |= _media_ids_in(value)
        return found
    if isinstance(node, list):
        found = set()
        for item in node:
            found |= _media_ids_in(item)
        return found
    return set()


def test_sections_without_images_reference_no_media() -> None:
    config = parse_config(
        _config({"id": "story", "type": "story", "props": {"heading": "H", "body": "b"}})
    )
    assert sections.referenced_media_ids(config.sections[0]) == []


def test_image_alt_bound_matches_the_catalog_and_media_contracts() -> None:
    """One alt-text bound across the product, pinned so none can drift."""
    assert (
        policies.MAX_IMAGE_ALT_LENGTH
        == catalog_policies.MAX_IMAGE_ALT_LENGTH
        == media_policies.MAX_IMAGE_ALT_LENGTH
    )
    with pytest.raises(ValidationError):
        parse_config(
            _config(
                _hero(
                    image={
                        "media_id": str(uuid.uuid4()),
                        "alt_text": "x" * (policies.MAX_IMAGE_ALT_LENGTH + 1),
                    }
                )
            )
        )
