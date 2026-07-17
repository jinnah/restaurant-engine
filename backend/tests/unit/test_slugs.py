"""Centralized slug policy and creation/resolution parity (M2C, ADR-013).

Both Business creation and public resolution consume the same policy source
(``app.domains.businesses.slugs``); these tests pin the reserved set and
prove the creation path rejects exactly the shared reserved labels.
"""

import pytest
from pydantic import ValidationError

from app.domains.businesses.schemas import BusinessCreate
from app.domains.businesses.slugs import (
    RESERVED_SLUGS,
    is_reserved,
    is_slug_shaped,
)


def test_reserved_set_is_exactly_the_approved_labels() -> None:
    # Guard against accidental expansion/contraction of the reserved set.
    assert RESERVED_SLUGS == frozenset({"api", "admin", "www"})


class TestSlugShape:
    @pytest.mark.parametrize("value", ["shalik", "a-b-c", "juniper-cafe", "x9y"])
    def test_valid_shapes(self, value: str) -> None:
        assert is_slug_shaped(value)

    @pytest.mark.parametrize("value", ["ab", "-bad", "bad-", "UPPER", "a_b", ""])
    def test_invalid_shapes(self, value: str) -> None:
        assert not is_slug_shaped(value)


class TestCreationResolutionParity:
    @pytest.mark.parametrize("label", sorted(RESERVED_SLUGS))
    def test_creation_rejects_every_reserved_label(self, label: str) -> None:
        # Same policy the resolver consults — a reserved label can never be
        # created, so it can never exist to (fail to) resolve.
        assert is_reserved(label)
        with pytest.raises(ValidationError) as exc_info:
            BusinessCreate(name="X", slug=label)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("slug",) for e in errors)
        # Generic message; never enumerates the reserved set.
        assert any("reserved" in str(e["msg"]).lower() for e in errors)
        assert all("api, admin, www" not in str(e["msg"]) for e in errors)

    def test_non_reserved_slug_is_accepted_and_canonicalized(self) -> None:
        created = BusinessCreate(name="Shalik", slug="  Shalik-Cafe  ")
        assert created.slug == "shalik-cafe"

    def test_reserved_check_runs_after_shape(self) -> None:
        # An edge-hyphen value (long enough to pass the length constraint)
        # fails on shape, not the reserved rule.
        with pytest.raises(ValidationError) as exc_info:
            BusinessCreate(name="X", slug="-bad")
        assert any("3-63" in str(e["msg"]) for e in exc_info.value.errors())
