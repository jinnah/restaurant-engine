"""Catalog policy constants, name normalization, and the dietary registry
(M3A, ADR-017 rulings R1/R2/R6/D6 + the F1 price ruling). Pure — no I/O."""

from app.api.audit_view import _choice, _price_int
from app.domains.catalog import dietary, policies


class TestPolicyConstants:
    """The approved ruling values are pinned: changing one is a deliberate
    ADR-017 amendment, not a drive-by edit."""

    def test_approved_bounds(self) -> None:
        assert policies.MAX_CATEGORIES_PER_BUSINESS == 50
        assert policies.MAX_ITEMS_PER_BUSINESS == 300
        assert policies.MAX_ITEMS_PER_CATEGORY == 100
        assert policies.MAX_DIETARY_TAGS_PER_ITEM == 3
        assert policies.MAX_FEATURED_ITEMS == 6
        assert policies.MAX_NAME_LENGTH == 120
        assert policies.MAX_CATEGORY_DESCRIPTION_LENGTH == 500
        assert policies.MAX_ITEM_DESCRIPTION_LENGTH == 1000

    def test_approved_price_bound(self) -> None:
        # F1 ruling: 0 <= price_minor <= 10,000,000 minor units.
        assert policies.MAX_PRICE_MINOR == 10_000_000

    def test_audit_price_extractor_retains_every_valid_price(self) -> None:
        # The projection shares the policy constant: the exact maximum is
        # retained; anything outside the approved range projects away.
        assert _price_int(policies.MAX_PRICE_MINOR) == policies.MAX_PRICE_MINOR
        assert _price_int(0) == 0
        assert _price_int(policies.MAX_PRICE_MINOR + 1) is None
        assert _price_int(-1) is None
        assert _price_int(True) is None


class TestNormalizeName:
    def test_trims_and_collapses_internal_whitespace(self) -> None:
        assert policies.normalize_name("  Rice   Bowl ") == "Rice Bowl"
        assert policies.normalize_name("A\t B\n C") == "A B C"

    def test_applies_unicode_nfc(self) -> None:
        # e + combining acute normalizes to the precomposed é.
        assert policies.normalize_name("Café") == "Café"

    def test_preserves_case_for_display(self) -> None:
        # Case-insensitive uniqueness is the DB expression index, not a
        # lowercased stored value.
        assert policies.normalize_name("Biryani Specials") == "Biryani Specials"

    def test_whitespace_only_becomes_empty(self) -> None:
        assert policies.normalize_name("   ") == ""


class TestDietaryRegistry:
    def test_seeded_with_exactly_the_approved_tags(self) -> None:
        assert {tag.value for tag in dietary.DietaryTag} == {
            "halal",
            "vegetarian",
            "vegan",
        }

    def test_known_and_unknown(self) -> None:
        assert dietary.is_known_tag("halal")
        assert not dietary.is_known_tag("Halal")  # canonical lowercase only
        assert not dietary.is_known_tag("spicy")
        assert not dietary.is_known_tag("")

    def test_filter_known_is_fail_closed_and_order_preserving(self) -> None:
        assert dietary.filter_known(["vegan", "spicy", "halal", ""]) == ["vegan", "halal"]


class TestModifierPolicyConstants:
    """M3B ruling values pinned (ADR-017 R2)."""

    def test_approved_modifier_bounds(self) -> None:
        assert policies.MAX_MODIFIER_GROUPS_PER_ITEM == 10
        assert policies.MAX_MODIFIER_GROUPS_PER_BUSINESS == 600
        assert policies.MAX_MODIFIER_OPTIONS_PER_GROUP == 30
        assert policies.MAX_MODIFIER_OPTIONS_PER_BUSINESS == 3000

    def test_options_cap_mirrors_the_selection_check_literal(self) -> None:
        # The modifier_groups min/max range CHECKs hard-code 30; this pin
        # keeps the code constant and the DB literal from drifting apart.
        assert policies.MAX_MODIFIER_OPTIONS_PER_GROUP == 30


class TestGroupSatisfiability:
    """The ruled formula (D5), exercised as a pure function."""

    def test_zero_active_options_is_never_satisfiable(self) -> None:
        assert not policies.is_group_satisfiable(0, None, 0)
        assert not policies.is_group_satisfiable(0, 1, 0)

    def test_optional_group_with_an_active_option_is_satisfiable(self) -> None:
        assert policies.is_group_satisfiable(0, None, 1)

    def test_required_group_needs_enough_active_options(self) -> None:
        assert not policies.is_group_satisfiable(2, None, 1)
        assert policies.is_group_satisfiable(2, None, 2)

    def test_finite_maximum_cannot_exceed_active_options(self) -> None:
        # docs/03: max cannot exceed selectable active options unless NULL.
        assert not policies.is_group_satisfiable(0, 5, 3)
        assert policies.is_group_satisfiable(0, 3, 3)
        assert policies.is_group_satisfiable(0, 1, 3)  # max below active is fine

    def test_unlimited_maximum_is_bounded_only_by_active_options(self) -> None:
        assert policies.is_group_satisfiable(1, None, 30)


class TestChoiceExtractor:
    """Closed-set audit projection extractor (M3B, D6 correction)."""

    def test_exact_members_pass(self) -> None:
        mode = _choice(frozenset({"finite", "unlimited"}))
        assert mode("finite") == "finite"
        assert mode("unlimited") == "unlimited"

    def test_everything_else_projects_away(self) -> None:
        mode = _choice(frozenset({"finite", "unlimited"}))
        assert mode("Finite") is None
        assert mode("infinite") is None
        assert mode("") is None
        assert mode(True) is None
        assert mode(1) is None
        assert mode({"finite": 1}) is None
        assert mode(None) is None
