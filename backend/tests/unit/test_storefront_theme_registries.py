"""Tenant-selected theme registries (M4G-A, ADR-024 §3)."""

import json
import re
from enum import StrEnum
from pathlib import Path

from app.domains.storefront import theme_registries
from app.domains.storefront.theme_registries import (
    DEFAULT_PALETTE,
    DEFAULT_TYPE_PAIRING,
    PaletteId,
    TypePairingId,
)
from app.domains.storefront.variants import DesignVariant

_CONTRACT = Path(__file__).resolve().parents[3] / "packages" / "api-client" / "openapi.json"


class TestPaletteRegistry:
    def test_ships_exactly_the_five_ruled_values_in_order(self) -> None:
        """Five permanent values, fixed by ADR-024 §3 rather than deferred.

        These identifiers enter the OpenAPI enum, stored configurations, and
        published snapshots, so renaming one later is a contract and data
        concern. Registry *growth* is routine and this assertion is expected
        to change then — deliberately, as a decision rather than as drift.
        """
        assert [palette.value for palette in PaletteId] == [
            "warm",
            "ember",
            "slate",
            "olive",
            "midnight",
        ]

    def test_the_default_is_explicit_and_registered(self) -> None:
        """No implicit 'first member of the enum' rule to drift."""
        assert DEFAULT_PALETTE is PaletteId.WARM
        assert theme_registries.is_known_palette(DEFAULT_PALETTE.value)

    def test_unknown_palettes_are_rejected(self) -> None:
        for rejected in ("", "WARM", " warm", "warm ", "crimson", "url(x)"):
            assert not theme_registries.is_known_palette(rejected)


class TestTypePairingRegistry:
    def test_ships_exactly_the_three_ruled_values_in_order(self) -> None:
        assert [pairing.value for pairing in TypePairingId] == [
            "humanist",
            "serif_display",
            "geometric",
        ]

    def test_the_default_is_explicit_and_registered(self) -> None:
        assert DEFAULT_TYPE_PAIRING is TypePairingId.HUMANIST
        assert theme_registries.is_known_type_pairing(DEFAULT_TYPE_PAIRING.value)

    def test_unknown_pairings_are_rejected(self) -> None:
        for rejected in ("", "HUMANIST", "serif-display", "editorial_serif", "sans"):
            assert not theme_registries.is_known_type_pairing(rejected)


class TestRegistryConventions:
    def test_both_registries_are_str_enums_like_every_other_registry(self) -> None:
        """The stored value is the member value, so JSONB round-trips it."""
        assert issubclass(PaletteId, StrEnum)
        assert issubclass(TypePairingId, StrEnum)

    def test_every_value_is_lowercase_snake_case_with_no_hyphen(self) -> None:
        """The repository-wide convention ADR-024 §3 cited as evidence.

        No hyphenated enum value exists anywhere in the backend domains
        (``view_menu``, ``online_ordering``), which is why the pairing is
        ``serif_display`` rather than ``editorial-serif``. Pinned so the
        next registry entry cannot quietly introduce the first exception.
        """
        for value in [p.value for p in PaletteId] + [t.value for t in TypePairingId]:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", value), value

    def test_the_three_registries_are_independent_axes(self) -> None:
        """Palette and pairing never collide with the design variant.

        Variant is platform-assigned; palette and pairing are tenant
        content. A shared identifier would imply a coupling that does not
        exist and would mislead every later reader (ADR-024 §3).
        """
        variant_values = {variant.value for variant in DesignVariant}
        assert variant_values.isdisjoint({p.value for p in PaletteId})
        assert variant_values.isdisjoint({t.value for t in TypePairingId})


class TestContractPublication:
    """The registries reach the client as closed enums (ADR-024 §3).

    Read from the committed artifact, so a registry change that is not
    regenerated fails here as well as in the contract drift check.
    """

    @staticmethod
    def _schemas() -> dict[str, dict[str, object]]:
        document = json.loads(_CONTRACT.read_text(encoding="utf-8"))
        schemas: dict[str, dict[str, object]] = document["components"]["schemas"]
        return schemas

    def test_palette_is_published_as_a_closed_enum(self) -> None:
        schema = self._schemas()["PaletteId"]
        assert schema["type"] == "string"
        assert schema["enum"] == [palette.value for palette in PaletteId]

    def test_type_pairing_is_published_as_a_closed_enum(self) -> None:
        schema = self._schemas()["TypePairingId"]
        assert schema["type"] == "string"
        assert schema["enum"] == [pairing.value for pairing in TypePairingId]

    def test_the_theme_publishes_the_registry_defaults(self) -> None:
        """The defaults are contract facts, which is what lets a client
        mirror them (the control-center composer does, pinned there too)."""
        properties = self._schemas()["Theme"]["properties"]
        assert isinstance(properties, dict)
        assert properties["palette"]["default"] == DEFAULT_PALETTE.value
        assert properties["type_pairing"]["default"] == DEFAULT_TYPE_PAIRING.value
