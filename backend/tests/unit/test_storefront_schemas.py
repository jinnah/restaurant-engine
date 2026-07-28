"""Storefront command schemas (M4B): intent representation and strictness.

The concurrency *behavior* is integration-tested; these pin the contract
shapes — the §5.4 create/update intent representation and the §5.10 rule
that owner/manager payloads structurally cannot carry ``design_variant``.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.storefront.schemas import DesignAssignment, DraftPut
from app.domains.storefront.variants import DesignVariant


def _config_payload(sections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "theme": {"accent": "#a34b2a"},
        "sections": sections or [],
    }


class TestDraftPutIntent:
    """§5.4: omitted-or-null is create intent; an integer is an update claim."""

    def test_omitted_lock_version_is_create_intent(self) -> None:
        payload = DraftPut.model_validate({"config": _config_payload()})
        assert payload.expected_lock_version is None

    def test_explicit_null_is_create_intent(self) -> None:
        payload = DraftPut.model_validate(
            {"config": _config_payload(), "expected_lock_version": None}
        )
        assert payload.expected_lock_version is None

    def test_zero_is_an_update_claim_distinct_from_create(self) -> None:
        # "I believe it is at 0" must stay distinguishable from "I believe
        # none exists" — a guessed 0 can never create.
        payload = DraftPut.model_validate({"config": _config_payload(), "expected_lock_version": 0})
        assert payload.expected_lock_version == 0

    def test_negative_lock_version_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DraftPut.model_validate({"config": _config_payload(), "expected_lock_version": -1})


class TestDraftPutStrictness:
    def test_design_variant_is_not_a_draft_field(self) -> None:
        # §5.10: the variant is platform-governed; submitting one is a 422
        # (extra_forbidden), never a silently ignored value.
        with pytest.raises(ValidationError) as excinfo:
            DraftPut.model_validate({"config": _config_payload(), "design_variant": "classic"})
        assert any(error["type"] == "extra_forbidden" for error in excinfo.value.errors())

    def test_unknown_top_level_property_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DraftPut.model_validate({"config": _config_payload(), "publish": True})

    def test_config_is_validated_by_the_registry(self) -> None:
        # One smoke case: the registry (M4A) does the real validation work.
        bad = _config_payload(
            sections=[{"id": "x-1", "type": "carousel", "enabled": True, "props": {}}]
        )
        with pytest.raises(ValidationError):
            DraftPut.model_validate({"config": bad})

    def test_config_is_required(self) -> None:
        with pytest.raises(ValidationError):
            DraftPut.model_validate({"expected_lock_version": 0})


class TestDesignAssignmentSchema:
    def test_registered_variant_is_accepted(self) -> None:
        payload = DesignAssignment.model_validate({"design_variant": "classic"})
        assert payload.design_variant is DesignVariant.CLASSIC

    def test_unregistered_variant_is_rejected(self) -> None:
        # The registry enum publishes the closed set in the contract: an
        # unknown variant is a 422 before the service runs.
        with pytest.raises(ValidationError):
            DesignAssignment.model_validate({"design_variant": "brutalist"})

    def test_no_lock_version_field_exists(self) -> None:
        # §6: the platform command carries no owner-facing lock_version.
        with pytest.raises(ValidationError):
            DesignAssignment.model_validate(
                {"design_variant": "classic", "expected_lock_version": 0}
            )
