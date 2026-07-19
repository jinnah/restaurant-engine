"""Catalog command-schema validation (M3A): strict commands, normalized
inputs, registry-validated dietary tags, and PATCH null semantics."""

import uuid

import pytest
from pydantic import ValidationError

from app.domains.catalog import policies
from app.domains.catalog.schemas import (
    CategoryCreate,
    CategoryReorder,
    CategoryUpdate,
    ItemAvailabilitySet,
    ItemCreate,
    ItemReorder,
    ItemUpdate,
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
    def test_dietary_tags_are_canonicalized(self) -> None:
        payload = ItemCreate(name="Samosa", price_minor=350, dietary_tags=[" Halal "])
        assert payload.dietary_tags == ["halal"]

    def test_unknown_dietary_tag_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown dietary tag"):
            ItemCreate(name="Samosa", price_minor=350, dietary_tags=["spicy"])

    def test_duplicate_tags_after_canonicalization_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate dietary tag"):
            ItemCreate(name="Samosa", price_minor=350, dietary_tags=["halal", "HALAL"])

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
