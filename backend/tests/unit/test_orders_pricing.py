"""The pure cart validation and pricing core (M6A, ADR-026).

Pure tests, no database: the checkout view is hand-built, so every §19
exit-criterion behavior — authoritative totals, graceful stale failures,
selection-rule enforcement — is proven deterministically. The placement
schema's text policy is pinned here too, because the core only ever sees
canonical text.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.domains.catalog.checkout_view import CheckoutGroup, CheckoutItem, CheckoutOption
from app.domains.orders import policies
from app.domains.orders.pricing import CartInvalidError, price_cart
from app.domains.orders.schemas import CartLineIn, OrderPlace


def _option(
    option_id: uuid.UUID | None = None, *, delta: int = 0, available: bool = True
) -> CheckoutOption:
    return CheckoutOption(
        id=option_id or uuid.uuid4(),
        name="Option",
        price_delta_minor=delta,
        is_available=available,
    )


def _group(
    *options: CheckoutOption,
    min_select: int = 0,
    max_select: int | None = None,
    group_id: uuid.UUID | None = None,
) -> CheckoutGroup:
    return CheckoutGroup(
        id=group_id or uuid.uuid4(),
        name="Group",
        min_select=min_select,
        max_select=max_select,
        options=tuple(options),
    )


def _item(
    item_id: uuid.UUID | None = None,
    *,
    price: int = 1000,
    visible: bool = True,
    available: bool = True,
    groups: tuple[CheckoutGroup, ...] = (),
) -> CheckoutItem:
    return CheckoutItem(
        id=item_id or uuid.uuid4(),
        display_name="Dish",
        price_minor=price,
        is_publicly_visible=visible,
        is_available=available,
        groups=groups,
    )


def _line(
    item: CheckoutItem, *, quantity: int = 1, options: list[uuid.UUID] | None = None
) -> CartLineIn:
    return CartLineIn(item_id=item.id, quantity=quantity, option_ids=options or [])


class TestPricing:
    def test_prices_come_from_the_view_and_totals_are_authoritative(self) -> None:
        extra = _option(delta=150)
        free = _option(delta=0)
        item = _item(price=1250, groups=(_group(extra, free),))
        cart = price_cart({item.id: item}, [_line(item, quantity=3, options=[extra.id, free.id])])
        (line,) = cart.lines
        assert line.base_price_minor == 1250
        assert line.line_total_minor == (1250 + 150) * 3
        assert cart.subtotal_minor == line.line_total_minor
        # Rulings D6/D7: total equals subtotal while tax and discounts
        # stay frozen at zero.
        assert cart.tax_minor == 0
        assert cart.total_minor == cart.subtotal_minor

    def test_snapshot_carries_display_names_and_provenance(self) -> None:
        option = _option(delta=25)
        group = _group(option)
        item = _item(groups=(group,))
        cart = price_cart({item.id: item}, [_line(item, options=[option.id])])
        (line,) = cart.lines
        (snap,) = line.options
        assert line.item_provenance_id == item.id
        assert line.display_name == "Dish"
        assert snap.group_provenance_id == group.id
        assert snap.option_provenance_id == option.id
        assert snap.group_display_name == "Group"
        assert snap.option_display_name == "Option"

    def test_multiple_lines_sum(self) -> None:
        a, b = _item(price=500), _item(price=750)
        cart = price_cart({a.id: a, b.id: b}, [_line(a, quantity=2), _line(b)])
        assert cart.subtotal_minor == 500 * 2 + 750
        assert [line.line_total_minor for line in cart.lines] == [1000, 750]

    def test_total_guard(self) -> None:
        # 9 lines x 50 qty x the catalog price cap exceeds MAX_TOTAL_MINOR.
        item = _item(price=10_000_000)
        assert 9 * 50 * 10_000_000 > policies.MAX_TOTAL_MINOR
        lines = [_line(item, quantity=50) for _ in range(9)]
        with pytest.raises(CartInvalidError) as excinfo:
            price_cart({item.id: item}, lines)
        assert [p.reason for p in excinfo.value.problems] == ["total_bounds"]


class TestStaleness:
    def test_unknown_and_hidden_items_are_one_answer(self) -> None:
        hidden = _item(visible=False)
        with pytest.raises(CartInvalidError) as excinfo:
            price_cart(
                {hidden.id: hidden},
                [_line(hidden), CartLineIn(item_id=uuid.uuid4(), quantity=1)],
            )
        assert [p.reason for p in excinfo.value.problems] == ["item_unknown", "item_unknown"]

    def test_sold_out_item(self) -> None:
        item = _item(available=False)
        with pytest.raises(CartInvalidError) as excinfo:
            price_cart({item.id: item}, [_line(item)])
        (problem,) = excinfo.value.problems
        assert problem.reason == "item_unavailable"
        assert problem.line_index == 0

    def test_unsatisfiable_required_group_refuses_the_item(self) -> None:
        # The projection's is_orderable formula, applied authoritatively.
        gone = _option(available=False)
        item = _item(groups=(_group(gone, min_select=1),))
        with pytest.raises(CartInvalidError) as excinfo:
            price_cart({item.id: item}, [_line(item)])
        assert [p.reason for p in excinfo.value.problems] == ["item_not_orderable"]

    def test_option_problems_are_each_named(self) -> None:
        ok = _option()
        gone = _option(available=False)
        item = _item(groups=(_group(ok, gone),))
        stranger = uuid.uuid4()
        with pytest.raises(CartInvalidError) as excinfo:
            price_cart(
                {item.id: item},
                [_line(item, options=[ok.id, ok.id, gone.id, stranger])],
            )
        reasons = sorted(p.reason for p in excinfo.value.problems)
        assert reasons == ["option_duplicate", "option_unavailable", "option_unknown"]

    def test_selection_rules_enforced_per_group(self) -> None:
        a, b = _option(), _option()
        required = _group(a, b, min_select=1, max_select=1)
        item = _item(groups=(required,))
        # Missing required selection.
        with pytest.raises(CartInvalidError) as unmet:
            price_cart({item.id: item}, [_line(item)])
        assert [p.reason for p in unmet.value.problems] == ["selection_rule"]
        assert unmet.value.problems[0].group_id == required.id
        # Above max.
        with pytest.raises(CartInvalidError) as over:
            price_cart({item.id: item}, [_line(item, options=[a.id, b.id])])
        assert [p.reason for p in over.value.problems] == ["selection_rule"]
        # Exactly right prices cleanly.
        cart = price_cart({item.id: item}, [_line(item, options=[a.id])])
        assert cart.total_minor == 1000

    def test_all_problems_reported_in_one_pass(self) -> None:
        sold_out = _item(available=False)
        fine = _item()
        with pytest.raises(CartInvalidError) as excinfo:
            price_cart(
                {sold_out.id: sold_out, fine.id: fine},
                [
                    _line(sold_out),
                    _line(fine, options=[uuid.uuid4()]),
                    CartLineIn(item_id=uuid.uuid4(), quantity=2),
                ],
            )
        assert [(p.line_index, p.reason) for p in excinfo.value.problems] == [
            (0, "item_unavailable"),
            (1, "option_unknown"),
            (2, "item_unknown"),
        ]


class TestPlacementSchema:
    def _payload(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "idempotency_key": str(uuid.uuid4()),
            "lines": [{"item_id": str(uuid.uuid4()), "quantity": 1}],
            "customer_name": "  Amina   Rahman ",
            "customer_phone": "(716) 555-0142",
            "customer_email": "",
            "order_instructions": "Ring the bell\n\n\nTwice",
            "consent_updates": True,
            "consent_marketing": False,
            "pickup_kind": "asap",
            "expected_total_minor": 1000,
        }
        base.update(overrides)
        return base

    def test_text_is_normalized_at_the_boundary(self) -> None:
        payload = OrderPlace.model_validate(self._payload())
        assert payload.customer_name == "Amina Rahman"
        assert payload.customer_email is None  # blank normalizes to absent
        assert payload.order_instructions == "Ring the bell\n\nTwice"

    def test_control_characters_are_rejected_never_stripped(self) -> None:
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(self._payload(customer_name="Amina\x00"))
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(self._payload(order_instructions="fine\x07"))

    def test_consents_are_required_and_independent(self) -> None:
        missing = self._payload()
        del missing["consent_marketing"]
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(missing)

    def test_pickup_shape_is_validated(self) -> None:
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(
                self._payload(pickup_kind="scheduled")  # no requested_pickup_at
            )
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(
                self._payload(requested_pickup_at="2026-09-01T17:00:00Z")  # asap + instant
            )
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(
                self._payload(
                    pickup_kind="scheduled",
                    requested_pickup_at="2026-09-01T17:00:00",  # naive instant
                )
            )

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(self._payload(tip_minor=500))

    def test_line_bounds(self) -> None:
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(self._payload(lines=[]))
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(
                self._payload(lines=[{"item_id": str(uuid.uuid4()), "quantity": 0}])
            )
        with pytest.raises(ValidationError):
            OrderPlace.model_validate(
                self._payload(lines=[{"item_id": str(uuid.uuid4()), "quantity": 51}])
            )
