"""Pure cart validation and pricing (M6A, ADR-026).

The M5 discipline applied to money: given the catalog checkout view and
the submitted cart, either return a fully priced, fully snapshotted order
draft or raise one typed error carrying every line-level problem found.
No database, no clock, no request — a function of its arguments, which is
what makes the §19 exit criteria ("totals are authoritative", "stale
items fail gracefully") exhaustively testable at the unit layer.

Server-authoritative by construction (blueprint §7.7): every price below
comes from the checkout view; nothing the client sent is ever used in
arithmetic. The client's ``expected_total_minor`` is compared by the
service *after* pricing (ruling D8), never consumed here.

Orderability is the public projection's own formula applied at order
time: the item must be publicly visible, available, and every required
group satisfiable — the projection's ``is_orderable`` was a display fact;
this is the authoritative check it deferred to (docs/03).
"""

import uuid
from dataclasses import dataclass, field

from app.domains.catalog.checkout_view import CheckoutItem
from app.domains.orders import policies
from app.domains.orders.schemas import CartLineIn


@dataclass(frozen=True)
class CartProblem:
    """One reason the submitted cart cannot become an order right now.

    ``line_index`` is the zero-based index into the submitted lines; None
    marks an order-level problem. ``reason`` is a closed vocabulary the
    storefront maps to honest copy; ids are echoed only when the client
    already sent them (no existence disclosure beyond the cart itself).
    """

    reason: str
    line_index: int | None = None
    item_id: uuid.UUID | None = None
    option_id: uuid.UUID | None = None
    group_id: uuid.UUID | None = None


class CartInvalidError(Exception):
    """The cart references menu state that no longer permits it (409)."""

    def __init__(self, problems: list[CartProblem]) -> None:
        super().__init__("cart cannot be priced against the current menu")
        self.problems = problems


@dataclass(frozen=True)
class PricedOption:
    group_provenance_id: uuid.UUID
    option_provenance_id: uuid.UUID
    group_display_name: str
    option_display_name: str
    price_delta_minor: int


@dataclass(frozen=True)
class PricedLine:
    item_provenance_id: uuid.UUID
    display_name: str
    base_price_minor: int
    quantity: int
    item_instructions: str | None
    options: tuple[PricedOption, ...]
    line_total_minor: int


@dataclass(frozen=True)
class PricedCart:
    """The authoritative snapshot a placement persists (rulings D1/D6)."""

    lines: tuple[PricedLine, ...] = field(default_factory=tuple)
    subtotal_minor: int = 0
    tax_minor: int = 0
    total_minor: int = 0


def price_cart(view: dict[uuid.UUID, CheckoutItem], lines: list[CartLineIn]) -> PricedCart:
    """Validate and price the whole cart, or raise with every problem.

    All problems are collected before raising, so one response tells the
    customer everything that changed rather than one surprise per retry.
    """
    problems: list[CartProblem] = []
    priced_lines: list[PricedLine] = []

    for index, line in enumerate(lines):
        item = view.get(line.item_id)
        if item is None or not item.is_publicly_visible:
            # Unknown, cross-business, hidden, and invisible-category are
            # one indistinguishable answer: this line no longer exists.
            problems.append(
                CartProblem(reason="item_unknown", line_index=index, item_id=line.item_id)
            )
            continue
        if not item.is_available:
            problems.append(
                CartProblem(reason="item_unavailable", line_index=index, item_id=line.item_id)
            )
            continue
        if any(group.is_required and not group.is_satisfiable for group in item.groups):
            # The projection would have shown is_orderable = false; at
            # order time it is a refusal, not a display fact.
            problems.append(
                CartProblem(reason="item_not_orderable", line_index=index, item_id=line.item_id)
            )
            continue

        options_by_id = {
            option.id: (group, option) for group in item.groups for option in group.options
        }
        line_ok = True

        seen: set[uuid.UUID] = set()
        for option_id in line.option_ids:
            if option_id in seen:
                problems.append(
                    CartProblem(reason="option_duplicate", line_index=index, option_id=option_id)
                )
                line_ok = False
            seen.add(option_id)
            resolved = options_by_id.get(option_id)
            if resolved is None:
                problems.append(
                    CartProblem(reason="option_unknown", line_index=index, option_id=option_id)
                )
                line_ok = False
            elif not resolved[1].is_available:
                problems.append(
                    CartProblem(reason="option_unavailable", line_index=index, option_id=option_id)
                )
                line_ok = False

        if line_ok:
            selected_by_group: dict[uuid.UUID, int] = {}
            for option_id in line.option_ids:
                group, _option = options_by_id[option_id]
                selected_by_group[group.id] = selected_by_group.get(group.id, 0) + 1
            for group in item.groups:
                count = selected_by_group.get(group.id, 0)
                if count < group.min_select or (
                    group.max_select is not None and count > group.max_select
                ):
                    problems.append(
                        CartProblem(reason="selection_rule", line_index=index, group_id=group.id)
                    )
                    line_ok = False

        if not line_ok:
            continue

        priced_options = tuple(
            PricedOption(
                group_provenance_id=options_by_id[option_id][0].id,
                option_provenance_id=option_id,
                group_display_name=options_by_id[option_id][0].name,
                option_display_name=options_by_id[option_id][1].name,
                price_delta_minor=options_by_id[option_id][1].price_delta_minor,
            )
            for option_id in line.option_ids
        )
        unit_price = item.price_minor + sum(o.price_delta_minor for o in priced_options)
        line_total = unit_price * line.quantity
        priced_lines.append(
            PricedLine(
                item_provenance_id=item.id,
                display_name=item.display_name,
                base_price_minor=item.price_minor,
                quantity=line.quantity,
                item_instructions=line.item_instructions,
                options=priced_options,
                line_total_minor=line_total,
            )
        )

    if problems:
        raise CartInvalidError(problems)

    subtotal = sum(line.line_total_minor for line in priced_lines)
    # Rulings D6/D7: tax and discounts exist as columns, frozen at zero,
    # so the §9.2 components identity holds from the first order onward.
    total = subtotal
    if total > policies.MAX_TOTAL_MINOR:
        raise CartInvalidError([CartProblem(reason="total_bounds")])
    return PricedCart(
        lines=tuple(priced_lines),
        subtotal_minor=subtotal,
        tax_minor=0,
        total_minor=total,
    )
