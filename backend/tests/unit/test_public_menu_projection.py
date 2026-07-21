"""Public menu projection rules (M3D, ADR-017).

Pure tests over detached ORM instances: the visibility, satisfiability,
and orderability rules are decided in Python, so they are provable without
a database. The database-backed shape, ordering, and isolation behavior
live in the integration suite.
"""

import uuid

import pytest

from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.catalog import policies, public_schemas, public_service
from app.domains.catalog.models import MenuItem, ModifierGroup, ModifierOption

# Fields that exist administratively (or in storage metadata) and must never
# appear on a public schema. Denylist, not allowlist: it keeps failing as the
# public contract grows.
_DENIED_PUBLIC_FIELDS = {
    # Administrative catalog state.
    "position",
    "is_hidden",
    "is_featured",
    "is_visible",
    "created_at",
    "updated_at",
    "business_id",
    "category_id",
    "item_id",
    "group_id",
    # Administrative modifier diagnostics.
    "active_option_count",
    "is_satisfiable",
    # Media internals (ADR-017 R3): identifiers, keys, checksums.
    "image_media_id",
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
    public_schemas.PublicMenu,
    public_schemas.PublicMenuCategory,
    public_schemas.PublicMenuItem,
    public_schemas.PublicMenuImage,
    public_schemas.PublicMenuImageVariant,
    public_schemas.PublicModifierGroup,
    public_schemas.PublicModifierOption,
)


def _group(*, min_select: int = 0, max_select: int | None = None) -> ModifierGroup:
    return ModifierGroup(
        id=uuid.uuid4(),
        business_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        name="Spice level",
        min_select=min_select,
        max_select=max_select,
        position=0,
    )


def _option(name: str = "Mild", price_delta_minor: int = 0) -> ModifierOption:
    return ModifierOption(
        id=uuid.uuid4(),
        business_id=uuid.uuid4(),
        group_id=uuid.uuid4(),
        name=name,
        price_delta_minor=price_delta_minor,
        is_available=True,
        position=0,
    )


def _item(*, is_available: bool = True) -> MenuItem:
    return MenuItem(
        id=uuid.uuid4(),
        business_id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        name="Samosa",
        description="Crisp pastry",
        price_minor=350,
        position=0,
        is_available=is_available,
        is_hidden=False,
        is_featured=False,
    )


class TestGroupProjection:
    def test_satisfiable_group_is_projected_with_its_options(self) -> None:
        group = _group(min_select=1, max_select=1)
        options = [_option("Mild"), _option("Hot", 50)]
        views, required_dropped = public_service._project_groups([group], {group.id: options})
        assert required_dropped is False
        assert [option.name for option in views[0].options] == ["Mild", "Hot"]
        assert views[0].min_select == 1
        assert views[0].max_select == 1

    def test_option_order_is_preserved_exactly_as_loaded(self) -> None:
        group = _group()
        options = [_option("A"), _option("B"), _option("C")]
        views, _ = public_service._project_groups([group], {group.id: options})
        assert [option.name for option in views[0].options] == ["A", "B", "C"]

    def test_group_with_no_available_options_is_omitted(self) -> None:
        group = _group(min_select=0)
        views, required_dropped = public_service._project_groups([group], {})
        assert views == []
        # Optional group: its absence must not block ordering.
        assert required_dropped is False

    def test_unsatisfiable_required_group_is_omitted_and_flags_the_item(self) -> None:
        group = _group(min_select=2)
        views, required_dropped = public_service._project_groups([group], {group.id: [_option()]})
        assert views == []
        assert required_dropped is True

    def test_finite_maximum_above_available_options_is_unsatisfiable(self) -> None:
        group = _group(min_select=0, max_select=3)
        views, required_dropped = public_service._project_groups([group], {group.id: [_option()]})
        assert views == []
        assert required_dropped is False

    def test_unlimited_maximum_with_one_option_is_satisfiable(self) -> None:
        group = _group(min_select=0, max_select=None)
        views, _ = public_service._project_groups([group], {group.id: [_option()]})
        assert len(views) == 1
        assert views[0].max_select is None

    def test_a_mix_projects_only_the_satisfiable_groups(self) -> None:
        good = _group(min_select=1, max_select=1)
        empty_optional = _group(min_select=0)
        broken_required = _group(min_select=5)
        views, required_dropped = public_service._project_groups(
            [good, empty_optional, broken_required],
            {good.id: [_option()], broken_required.id: [_option()]},
        )
        assert [view.id for view in views] == [good.id]
        assert required_dropped is True

    def test_projection_uses_the_shared_satisfiability_policy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """There must be exactly one satisfiability formula (ADR-017 D5).

        Forcing the shared policy to reject everything must empty the
        projection; if the public path had its own copy of the rule, the
        group would survive and this fails.
        """
        calls: list[tuple[int, int | None, int]] = []

        def _never(min_select: int, max_select: int | None, active_count: int) -> bool:
            calls.append((min_select, max_select, active_count))
            return False

        monkeypatch.setattr(policies, "is_group_satisfiable", _never)
        group = _group(min_select=1, max_select=2)
        views, _ = public_service._project_groups([group], {group.id: [_option(), _option("Hot")]})
        assert views == []
        # The active-option count handed to the policy is the number of
        # publicly available options, not the stored option count.
        assert calls == [(1, 2, 2)]


class TestItemProjection:
    def test_available_item_without_broken_groups_is_orderable(self) -> None:
        view = public_service._item_view(_item(), [], [], None, required_group_unsatisfiable=False)
        assert view.is_available is True
        assert view.is_orderable is True

    def test_sold_out_item_stays_listed_but_is_not_orderable(self) -> None:
        view = public_service._item_view(
            _item(is_available=False), [], [], None, required_group_unsatisfiable=False
        )
        assert view.is_available is False
        assert view.is_orderable is False

    def test_unsatisfiable_required_group_makes_an_available_item_unorderable(self) -> None:
        view = public_service._item_view(_item(), [], [], None, required_group_unsatisfiable=True)
        assert view.is_available is True
        assert view.is_orderable is False

    def test_sold_out_and_broken_required_group_is_still_just_unorderable(self) -> None:
        view = public_service._item_view(
            _item(is_available=False), [], [], None, required_group_unsatisfiable=True
        )
        assert view.is_orderable is False

    def test_dietary_tags_are_registry_filtered(self) -> None:
        view = public_service._item_view(
            _item(),
            ["halal", "not-a-real-tag", "vegan"],
            [],
            None,
            required_group_unsatisfiable=False,
        )
        assert view.dietary_tags == ["halal", "vegan"]

    def test_item_projection_exposes_no_administrative_field(self) -> None:
        view = public_service._item_view(
            _item(), ["halal"], [], None, required_group_unsatisfiable=False
        )
        assert set(view.model_dump()) == {
            "id",
            "name",
            "description",
            "price_minor",
            "is_available",
            "is_orderable",
            "dietary_tags",
            "image",
            "modifier_groups",
        }


class TestPublicSchemasCarryNoInternalField:
    """The public contract must not inherit administrative or storage fields.

    A denylist rather than an allowlist: it keeps failing as the schemas
    grow, which is exactly when an internal field is most likely to be
    added by reflex.
    """

    def test_no_public_schema_declares_a_denied_field(self) -> None:
        for model in _PUBLIC_MODELS:
            offending = set(model.model_fields) & _DENIED_PUBLIC_FIELDS
            assert offending == set(), f"{model.__name__} exposes {sorted(offending)}"

    def test_currency_is_only_reachable_through_the_business_summary(self) -> None:
        assert "currency" not in public_schemas.PublicMenu.model_fields
        assert "currency" not in public_schemas.PublicMenuItem.model_fields
        assert public_schemas.PublicMenu.model_fields["business"].annotation is PublicSiteSummary
        assert "currency" in PublicSiteSummary.model_fields
