"""Design-variant registry (M4A, ADR-020)."""

from app.domains.storefront import variants
from app.domains.storefront.variants import PLATFORM_DEFAULT_VARIANT, DesignVariant


def test_the_registry_is_closed_and_ships_exactly_one_variant() -> None:
    """One variant in M4A, deliberately.

    A variant is a *renderer* contract and no renderer exists before M4D;
    naming more now would publish structure nothing can render. This test
    is expected to change when M4D adds real variants — it exists so that
    happens as a decision, not as drift.
    """
    assert {variant.value for variant in DesignVariant} == {"classic"}


def test_the_platform_default_is_explicit_and_registered() -> None:
    """No implicit 'first member of the enum' rule to drift."""
    assert PLATFORM_DEFAULT_VARIANT is DesignVariant.CLASSIC
    assert variants.is_known_variant(PLATFORM_DEFAULT_VARIANT.value)


def test_unknown_variants_are_rejected() -> None:
    for rejected in ("", "CLASSIC", " classic", "modern", "custom.css"):
        assert not variants.is_known_variant(rejected)


def test_variant_values_are_storable_in_the_design_variant_column() -> None:
    """Every registered value satisfies the non-empty database CHECK."""
    assert all(variant.value for variant in DesignVariant)
