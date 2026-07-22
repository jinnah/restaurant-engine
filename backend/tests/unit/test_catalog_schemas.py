"""Catalog command-schema validation (M3A): strict commands, normalized
inputs, registry-validated dietary tags, and PATCH null semantics."""

import json
import uuid

import pytest
from pydantic import ValidationError

from app.domains.catalog import policies
from app.domains.catalog.dietary import DietaryTag
from app.domains.catalog.schemas import (
    CategoryCreate,
    CategoryReorder,
    CategoryUpdate,
    ItemAvailabilitySet,
    ItemCreate,
    ItemReorder,
    ItemUpdate,
    ModifierGroupCreate,
    ModifierGroupReorder,
    ModifierGroupUpdate,
    ModifierOptionCreate,
    ModifierOptionReorder,
    ModifierOptionUpdate,
)


class TestCategoryCreate:
    def test_name_is_normalized(self) -> None:
        payload = CategoryCreate(name="  Rice   Bowls ")
        assert payload.name == "Rice Bowls"

    def test_blank_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            CategoryCreate(name="   ")

    def test_overlong_name_is_rejected_after_normalization(self) -> None:
        with pytest.raises(ValidationError, match="at most"):
            CategoryCreate(name="x" * (policies.MAX_NAME_LENGTH + 1))

    def test_empty_description_becomes_none(self) -> None:
        assert CategoryCreate(name="Curries", description="   ").description is None

    def test_overlong_description_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most"):
            CategoryCreate(
                name="Curries",
                description="d" * (policies.MAX_CATEGORY_DESCRIPTION_LENGTH + 1),
            )

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CategoryCreate.model_validate({"name": "Curries", "position": 3})


class TestCategoryUpdate:
    def test_explicit_null_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be null"):
            CategoryUpdate.model_validate({"name": None})

    def test_explicit_null_visibility_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be null"):
            CategoryUpdate.model_validate({"is_visible": None})

    def test_explicit_null_description_clears(self) -> None:
        payload = CategoryUpdate.model_validate({"description": None})
        assert "description" in payload.model_fields_set
        assert payload.description is None


class TestItemCreate:
    # Dietary tags arrive as untyped wire JSON, so these go through
    # model_validate rather than the typed constructor: the declared type is
    # the DietaryTag registry (M3E contract-fidelity correction) while the
    # mode="before" validator still accepts and canonicalizes raw strings.
    def test_dietary_tags_are_canonicalized(self) -> None:
        payload = ItemCreate.model_validate(
            {"name": "Samosa", "price_minor": 350, "dietary_tags": [" Halal "]}
        )
        assert payload.dietary_tags == [DietaryTag.HALAL]
        assert payload.dietary_tags == ["halal"]  # StrEnum: still equals the stored value

    def test_dietary_tags_serialize_as_canonical_strings(self) -> None:
        payload = ItemCreate.model_validate(
            {"name": "Samosa", "price_minor": 350, "dietary_tags": ["VEGAN", " vegetarian"]}
        )
        assert json.loads(payload.model_dump_json())["dietary_tags"] == ["vegan", "vegetarian"]

    def test_recognized_tags_are_accepted(self) -> None:
        payload = ItemCreate.model_validate(
            {
                "name": "Samosa",
                "price_minor": 350,
                "dietary_tags": ["halal", "vegetarian", "vegan"],
            }
        )
        assert payload.dietary_tags == [
            DietaryTag.HALAL,
            DietaryTag.VEGETARIAN,
            DietaryTag.VEGAN,
        ]

    def test_unknown_dietary_tag_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown dietary tag"):
            ItemCreate.model_validate(
                {"name": "Samosa", "price_minor": 350, "dietary_tags": ["spicy"]}
            )

    def test_duplicate_tags_after_canonicalization_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate dietary tag"):
            ItemCreate.model_validate(
                {"name": "Samosa", "price_minor": 350, "dietary_tags": ["halal", "HALAL"]}
            )

    def test_non_string_dietary_tag_surfaces_the_declared_type_error(self) -> None:
        # The before-validator hands a non-string list straight to the declared
        # type, so Pydantic reports the type problem rather than an
        # attribute error from inside normalization.
        with pytest.raises(ValidationError) as excinfo:
            ItemCreate.model_validate({"name": "Samosa", "price_minor": 350, "dietary_tags": [7]})
        assert "dietary_tags" in str(excinfo.value)

    def test_non_list_dietary_tags_surface_the_declared_type_error(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            ItemCreate.model_validate(
                {"name": "Samosa", "price_minor": 350, "dietary_tags": "halal"}
            )
        assert "dietary_tags" in str(excinfo.value)

    def test_negative_price_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name="Samosa", price_minor=-1)

    def test_price_at_the_exact_maximum_is_accepted(self) -> None:
        payload = ItemCreate(name="Banquet", price_minor=policies.MAX_PRICE_MINOR)
        assert payload.price_minor == 10_000_000

    def test_price_above_ceiling_is_rejected(self) -> None:
        # 10,000,001 fails on create and on update alike (F1 ruling).
        with pytest.raises(ValidationError):
            ItemCreate(name="Samosa", price_minor=policies.MAX_PRICE_MINOR + 1)
        with pytest.raises(ValidationError):
            ItemUpdate(price_minor=policies.MAX_PRICE_MINOR + 1)


class TestItemUpdate:
    def test_availability_is_not_part_of_the_patch_contract(self) -> None:
        # Ruling D4: availability is the separate command; a PATCH carrying
        # it is rejected by the strict schema, never silently ignored.
        with pytest.raises(ValidationError):
            ItemUpdate.model_validate({"is_available": False})

    def test_explicit_null_price_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be null"):
            ItemUpdate.model_validate({"price_minor": None})

    def test_explicit_null_tags_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be null"):
            ItemUpdate.model_validate({"dietary_tags": None})


class TestReorderPayloads:
    def test_duplicate_ids_are_rejected(self) -> None:
        duplicate = uuid.uuid4()
        with pytest.raises(ValidationError, match="duplicates"):
            CategoryReorder(ordered_category_ids=[duplicate, duplicate])
        with pytest.raises(ValidationError, match="duplicates"):
            ItemReorder(category_id=uuid.uuid4(), ordered_item_ids=[duplicate, duplicate])

    def test_payloads_are_bounded_by_the_scope_limit(self) -> None:
        category_cap = policies.MAX_CATEGORIES_PER_BUSINESS
        too_many_categories = [uuid.uuid4() for _ in range(category_cap + 1)]
        with pytest.raises(ValidationError):
            CategoryReorder(ordered_category_ids=too_many_categories)
        too_many_items = [uuid.uuid4() for _ in range(policies.MAX_ITEMS_PER_CATEGORY + 1)]
        with pytest.raises(ValidationError):
            ItemReorder(category_id=uuid.uuid4(), ordered_item_ids=too_many_items)

    def test_empty_reorder_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CategoryReorder(ordered_category_ids=[])


class TestAvailabilityCommand:
    def test_requires_the_flag(self) -> None:
        with pytest.raises(ValidationError):
            ItemAvailabilitySet.model_validate({})

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemAvailabilitySet.model_validate({"is_available": True, "is_hidden": True})


class TestModifierGroupCreate:
    def test_defaults_are_optional_unlimited(self) -> None:
        payload = ModifierGroupCreate(name="Spice Level")
        assert payload.min_select == 0
        assert payload.max_select is None

    def test_name_is_normalized(self) -> None:
        assert ModifierGroupCreate(name="  Spice   Level ").name == "Spice Level"

    def test_selection_domain_bounds(self) -> None:
        ModifierGroupCreate(name="G", min_select=30, max_select=30)  # at the cap
        with pytest.raises(ValidationError):
            ModifierGroupCreate(name="G", min_select=31)
        with pytest.raises(ValidationError):
            ModifierGroupCreate(name="G", max_select=31)
        with pytest.raises(ValidationError):
            ModifierGroupCreate(name="G", min_select=-1)
        with pytest.raises(ValidationError):
            ModifierGroupCreate(name="G", max_select=0)

    def test_finite_min_above_max_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot exceed"):
            ModifierGroupCreate(name="G", min_select=3, max_select=2)


class TestModifierGroupUpdate:
    def test_explicit_null_max_means_unlimited(self) -> None:
        payload = ModifierGroupUpdate.model_validate({"max_select": None})
        assert "max_select" in payload.model_fields_set
        assert payload.max_select is None

    def test_explicit_null_name_or_min_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot be null"):
            ModifierGroupUpdate.model_validate({"name": None})
        with pytest.raises(ValidationError, match="cannot be null"):
            ModifierGroupUpdate.model_validate({"min_select": None})

    def test_pair_supplied_together_is_validated(self) -> None:
        with pytest.raises(ValidationError, match="cannot exceed"):
            ModifierGroupUpdate.model_validate({"min_select": 5, "max_select": 4})


class TestModifierOptionSchemas:
    def test_option_create_defaults_and_delta_bounds(self) -> None:
        payload = ModifierOptionCreate(name="Extra Chicken")
        assert payload.price_delta_minor == 0
        ModifierOptionCreate(name="Feast", price_delta_minor=policies.MAX_PRICE_MINOR)
        with pytest.raises(ValidationError):
            ModifierOptionCreate(name="X", price_delta_minor=policies.MAX_PRICE_MINOR + 1)
        with pytest.raises(ValidationError):
            ModifierOptionCreate(name="X", price_delta_minor=-1)

    def test_availability_is_not_a_create_field(self) -> None:
        with pytest.raises(ValidationError):
            ModifierOptionCreate.model_validate({"name": "X", "is_available": False})

    def test_option_update_rejects_explicit_nulls(self) -> None:
        for field in ("name", "price_delta_minor", "is_available"):
            with pytest.raises(ValidationError, match="cannot be null"):
                ModifierOptionUpdate.model_validate({field: None})


class TestModifierReorderSchemas:
    def test_duplicates_and_bounds(self) -> None:
        duplicate = uuid.uuid4()
        with pytest.raises(ValidationError, match="duplicates"):
            ModifierGroupReorder(ordered_group_ids=[duplicate, duplicate])
        with pytest.raises(ValidationError, match="duplicates"):
            ModifierOptionReorder(ordered_option_ids=[duplicate, duplicate])
        with pytest.raises(ValidationError):
            ModifierGroupReorder(
                ordered_group_ids=[
                    uuid.uuid4() for _ in range(policies.MAX_MODIFIER_GROUPS_PER_ITEM + 1)
                ]
            )
        with pytest.raises(ValidationError):
            ModifierOptionReorder(
                ordered_option_ids=[
                    uuid.uuid4() for _ in range(policies.MAX_MODIFIER_OPTIONS_PER_GROUP + 1)
                ]
            )
        with pytest.raises(ValidationError):
            ModifierGroupReorder(ordered_group_ids=[])
