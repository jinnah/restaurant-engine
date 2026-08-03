"""Orders application service (M6A, ADR-026).

Owns the one placement transaction (blueprint §14.1), in this order:
entitlement and pickup gate (neutral 404, ruling D10) → idempotency
lookup (a replay is a read, ruling D2) → catalog checkout view → pure
validation and pricing → Business ``FOR UPDATE`` (ruling D5: the lock
that makes order numbering and the D3 slot count race-free) → lifecycle
re-check → pickup promise and throttle → inserts (order, lines, options,
the ``→ submitted`` event, the outbox message, the idempotency row) →
audit → commit. No external network call exists to hold open.

The wall clock enters exactly once, as ``now`` at the top of placement;
every derived fact (promise, slot validity) is a pure function of it.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode, InvalidStateError, ResourceNotFoundError
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import (
    OrderCancelledByCustomerDetails,
    OrderEstimateSetDetails,
    OrderPlacedDetails,
    OrderTransitionDetails,
)
from app.domains.businesses import repository as businesses_repository
from app.domains.businesses.entitlements import business_has_feature
from app.domains.businesses.features import FeatureKey
from app.domains.businesses.lifecycle import BusinessStatus
from app.domains.businesses.models import Business
from app.domains.businesses.resolution import ResolvedBusiness
from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.catalog.checkout_view import checkout_view
from app.domains.hours import policies as hours_policies
from app.domains.hours import repository as hours_repository
from app.domains.hours.availability import (
    ExceptionDay,
    next_pickup_at,
    ordering_effectively_paused,
    pickup_slots,
)
from app.domains.hours.service import effective_policy
from app.domains.hours.timekeeping import local_date
from app.domains.identity.actor import ActorContext
from app.domains.identity.authorization import require_membership_capability
from app.domains.identity.policies import Capability
from app.domains.orders import policies, repository
from app.domains.orders.lifecycle import (
    ESTIMATE_LEGAL_STATUSES,
    MEMBER_TRANSITIONS,
    SLOT_RELEASING_STATUSES,
    OrderStatus,
    PickupKind,
    StatusActorKind,
)
from app.domains.orders.models import (
    IdempotencyKey,
    Order,
    OrderLine,
    OrderLineOption,
    OrderStatusEvent,
    OutboxMessage,
)
from app.domains.orders.pricing import CartInvalidError, PricedCart, PricedOption, price_cart
from app.domains.orders.schemas import (
    AdminOrderDetail,
    AdminOrderList,
    AdminOrderSummary,
    OrderEstimateSet,
    OrderMetrics,
    OrderPlace,
    OrderPlacedResponse,
    PopularItem,
    PublicOrderLine,
    PublicOrderLineOption,
    PublicOrderView,
    PublicPickupSlots,
    StatusEventView,
)

OUTBOX_TOPIC_ORDER_PLACED = "order.placed"


def _request_digest(payload: OrderPlace) -> str:
    """The canonical payload digest an idempotency row pins (ruling D2).

    Computed over the *validated, normalized* command with the key itself
    excluded, so an honest retry (same cart, same key) matches even when
    raw bytes differed, and key reuse with a different cart cannot.
    """
    canonical = payload.model_dump_json(exclude={"idempotency_key"})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _new_tracking_token() -> tuple[str, str]:
    """A 256-bit tracking token and its stored digest (ruling D4)."""
    token = secrets.token_urlsafe(policies.TRACKING_TOKEN_BYTES)
    return token, hashlib.sha256(token.encode("ascii")).hexdigest()


def _cart_problem_details(error: CartInvalidError) -> dict[str, object]:
    return {
        "problems": [
            {
                "reason": problem.reason,
                **({} if problem.line_index is None else {"line_index": problem.line_index}),
                **({} if problem.item_id is None else {"item_id": str(problem.item_id)}),
                **({} if problem.option_id is None else {"option_id": str(problem.option_id)}),
                **({} if problem.group_id is None else {"group_id": str(problem.group_id)}),
            }
            for problem in error.problems
        ]
    }


def _order_view(db: Session, business: ResolvedBusiness, order: Order) -> PublicOrderView:
    """Project one order from its stored snapshot — catalog is never read."""
    lines = repository.list_lines(db, business_id=business.business_id, order_id=order.id)
    options = repository.list_options_for_lines(
        db, business_id=business.business_id, line_ids=[line.id for line in lines]
    )
    return PublicOrderView(
        business=PublicSiteSummary(
            name=business.name,
            slug=business.slug,
            timezone=business.timezone,
            currency=business.currency,
        ),
        order_number=order.order_number,
        status=OrderStatus(order.status),
        placed_at=order.placed_at,
        business_timezone=order.business_timezone,
        pickup_kind=PickupKind(order.pickup_kind),
        promised_pickup_at=order.promised_pickup_at,
        estimated_ready_at=order.estimated_ready_at,
        currency=order.currency,
        subtotal_minor=order.subtotal_minor,
        tax_minor=order.tax_minor,
        total_minor=order.total_minor,
        lines=[
            PublicOrderLine(
                display_name=line.display_name,
                quantity=line.quantity,
                base_price_minor=line.base_price_minor,
                options=[
                    PublicOrderLineOption(
                        group_name=option.group_display_name,
                        option_name=option.option_display_name,
                        price_delta_minor=option.price_delta_minor,
                    )
                    for option in options.get(line.id, [])
                ],
                line_total_minor=line.line_total_minor,
            )
            for line in lines
        ],
    )


def _require_ordering_enabled(db: Session, business: ResolvedBusiness) -> None:
    """The D10 gate: no entitlement or no pickup is the one neutral 404.

    The API discloses no capability the storefront page does not show —
    a business without ordering simply has no ordering surface.
    """
    if not business_has_feature(db, business.business_id, FeatureKey.ONLINE_ORDERING):
        raise ResourceNotFoundError("Not found.")
    if not effective_policy(db, business.business_id).pickup_enabled:
        raise ResourceNotFoundError("Not found.")


def _hours_inputs(
    db: Session, business: ResolvedBusiness
) -> tuple[dict[int, list[tuple[int, int]]], dict[date, ExceptionDay], ZoneInfo]:
    """The pure slot-service inputs for this business, read once."""
    tz = ZoneInfo(business.timezone)
    today = local_date(datetime.now(UTC), tz)
    weekly: dict[int, list[tuple[int, int]]] = {}
    for row in hours_repository.list_weekly(db, business_id=business.business_id):
        weekly.setdefault(row.day_of_week, []).append((row.opens_minute, row.closes_minute))
    exceptions: dict[date, ExceptionDay] = {}
    rows = hours_repository.list_exceptions(
        db,
        business_id=business.business_id,
        start=today - timedelta(days=1),
        end=today + timedelta(days=hours_policies.EXCEPTION_FUTURE_WINDOW_DAYS),
    )
    grouped: dict[date, list[tuple[int, int]]] = {}
    notes: dict[date, str | None] = {}
    for exception_row in rows:
        grouped.setdefault(exception_row.exception_date, [])
        if exception_row.opens_minute is not None and exception_row.closes_minute is not None:
            grouped[exception_row.exception_date].append(
                (exception_row.opens_minute, exception_row.closes_minute)
            )
        notes.setdefault(exception_row.exception_date, exception_row.note)
    for day, intervals in grouped.items():
        exceptions[day] = ExceptionDay(
            exception_date=day, intervals=tuple(sorted(intervals)), note=notes[day]
        )
    return weekly, exceptions, tz


def _resolve_promise(
    db: Session,
    business: ResolvedBusiness,
    payload: OrderPlace,
    now: datetime,
) -> datetime:
    """The pickup promise: ASAP's next slot, or a revalidated scheduled slot.

    Scheduled validity is **recomputed** from the stored schedule and
    policy through the same pure machinery — never trusted from a list
    previously shown to the client (§4 of the ADR).
    """
    policy = effective_policy(db, business.business_id)
    weekly, exceptions, tz = _hours_inputs(db, business)
    if payload.pickup_kind is PickupKind.ASAP:
        if not policy.asap_enabled:
            raise ApiError(
                409,
                ErrorCode.SLOT_UNAVAILABLE,
                "As-soon-as-possible pickup is not offered right now.",
            )
        promise = next_pickup_at(now, weekly=weekly, exceptions=exceptions, policy=policy, tz=tz)
        if promise is None:
            raise ApiError(
                409,
                ErrorCode.SLOT_UNAVAILABLE,
                "No pickup time is currently available.",
            )
        return promise
    requested = payload.requested_pickup_at
    assert requested is not None  # noqa: S101 - schema model_validator guarantees
    requested = requested.astimezone(UTC)
    valid = pickup_slots(
        now,
        weekly=weekly,
        exceptions=exceptions,
        policy=policy,
        tz=tz,
        limit=policies.MAX_PUBLIC_SLOTS,
    )
    if requested not in valid:
        raise ApiError(
            409,
            ErrorCode.SLOT_UNAVAILABLE,
            "That pickup time is no longer available.",
            details={"requested_pickup_at": requested.isoformat()},
        )
    return requested


def place_order(
    db: Session, business: ResolvedBusiness, payload: OrderPlace
) -> tuple[OrderPlacedResponse, bool]:
    """Place one order idempotently; returns (response, created).

    A replay returns the current representation of the stored order with
    an empty token (the token is disclosed exactly once, at creation —
    ruling D4); the router maps ``created`` to 201 versus 200.
    """
    now = datetime.now(UTC)
    _require_ordering_enabled(db, business)

    digest = _request_digest(payload)
    existing = repository.get_idempotency(
        db,
        business_id=business.business_id,
        operation=policies.IDEMPOTENCY_OPERATION_PLACE,
        idempotency_key=payload.idempotency_key,
    )
    if existing is not None:
        return _replay(db, business, existing, digest), False

    # The D8 pause (M7A, ADR-027): a temporary, customer-visible refusal
    # — typed, never the neutral 404, and AFTER the replay lookup (an
    # honest retry of an order placed before the pause still reads).
    pause_policy = effective_policy(db, business.business_id)
    if ordering_effectively_paused(pause_policy, now):
        raise ApiError(
            409,
            ErrorCode.ORDERING_PAUSED,
            "Online ordering is temporarily paused.",
            details={
                **({} if pause_policy.pause_note is None else {"note": pause_policy.pause_note}),
                **(
                    {}
                    if pause_policy.pause_resume_at is None
                    else {"resume_at": pause_policy.pause_resume_at.isoformat()}
                ),
            },
        )

    view = checkout_view(
        db,
        business_id=business.business_id,
        item_ids=[line.item_id for line in payload.lines],
    )
    try:
        priced = price_cart(view, payload.lines)
    except CartInvalidError as error:
        raise ApiError(
            409,
            ErrorCode.CART_STALE,
            "The menu changed while you were ordering.",
            details=_cart_problem_details(error),
        ) from error
    if priced.total_minor != payload.expected_total_minor:
        raise ApiError(
            409,
            ErrorCode.PRICE_CHANGED,
            "Prices changed while you were ordering.",
            details={
                "expected_total_minor": payload.expected_total_minor,
                "total_minor": priced.total_minor,
                "subtotal_minor": priced.subtotal_minor,
            },
        )

    # The deterministic tenant lock (ruling D5): numbering and the D3
    # count are race-free behind it, and the lifecycle is pinned.
    locked = businesses_repository.get_for_update(db, business.business_id)
    if locked is None or locked.status != BusinessStatus.ACTIVE.value:
        raise ResourceNotFoundError("Not found.")

    promise = _resolve_promise(db, business, payload, now)
    policy = effective_policy(db, business.business_id)
    if policy.max_orders_per_slot is not None:
        taken = repository.count_orders_for_slot(
            db, business_id=business.business_id, promised_pickup_at=promise
        )
        if taken >= policy.max_orders_per_slot:
            raise ApiError(
                409,
                ErrorCode.SLOT_UNAVAILABLE,
                "That pickup time is fully booked.",
                details={"promised_pickup_at": promise.isoformat()},
            )

    token, token_digest = _new_tracking_token()
    # Explicit ids: the snapshot rows reference the order and line ids
    # before any flush, so the ids must exist at construction.
    order = Order(
        id=uuid.uuid4(),
        business_id=business.business_id,
        order_number=repository.next_order_number(db, business_id=business.business_id),
        tracking_token_digest=token_digest,
        status=OrderStatus.SUBMITTED.value,
        placed_at=now,
        business_timezone=business.timezone,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        order_instructions=payload.order_instructions,
        consent_updates=payload.consent_updates,
        consent_marketing=payload.consent_marketing,
        pickup_kind=payload.pickup_kind.value,
        promised_pickup_at=promise,
        currency=business.currency,
        subtotal_minor=priced.subtotal_minor,
        tax_minor=priced.tax_minor,
        discount_total_minor=0,
        total_minor=priced.total_minor,
        applied_promotions=[],
    )
    repository.add(db, order)
    # Explicit flush points: the orders mappers deliberately declare no
    # relationship() links (snapshots are data, not an object graph), and
    # the unit of work orders INSERTs by relationship dependency — bare
    # FK metadata alone does not sequence mappers. Each flush pins the
    # parent rows before their dependents are added.
    db.flush()
    _persist_snapshot(db, business.business_id, order, priced)
    repository.add(
        db,
        OrderStatusEvent(
            business_id=business.business_id,
            order_id=order.id,
            from_status=None,
            to_status=OrderStatus.SUBMITTED.value,
            actor_kind=StatusActorKind.CUSTOMER.value,
            actor_user_id=None,
        ),
    )
    repository.add(
        db,
        OutboxMessage(
            business_id=business.business_id,
            topic=OUTBOX_TOPIC_ORDER_PLACED,
            order_id=order.id,
            # Ids and facts only — never PII (ruling D14 / §16.1).
            payload={
                "order_id": str(order.id),
                "business_id": str(business.business_id),
                "order_number": order.order_number,
                "placed_at": now.isoformat(),
            },
        ),
    )
    repository.add(
        db,
        IdempotencyKey(
            business_id=business.business_id,
            operation=policies.IDEMPOTENCY_OPERATION_PLACE,
            idempotency_key=payload.idempotency_key,
            request_digest=digest,
            order_id=order.id,
        ),
    )
    recorder.record(
        db,
        AuditAction.ORDER_PLACED,
        actor_user_id=None,
        business_id=business.business_id,
        target_type="order",
        target_id=str(order.id),
        details=OrderPlacedDetails(
            order_number=order.order_number,
            line_count=len(priced.lines),
            total_minor=priced.total_minor,
            pickup_kind=payload.pickup_kind.value,
        ),
    )
    try:
        db.commit()
    except IntegrityError:
        # The concurrent-duplicate race (§4): another transaction with the
        # same key won the unique insert. Their order is the answer.
        db.rollback()
        winner = repository.get_idempotency(
            db,
            business_id=business.business_id,
            operation=policies.IDEMPOTENCY_OPERATION_PLACE,
            idempotency_key=payload.idempotency_key,
        )
        if winner is None:
            raise
        return _replay(db, business, winner, digest), False
    return (
        OrderPlacedResponse(tracking_token=token, order=_order_view(db, business, order)),
        True,
    )


def _persist_snapshot(
    db: Session, business_id: uuid.UUID, order: Order, priced: PricedCart
) -> None:
    rows: list[tuple[OrderLine, tuple[PricedOption, ...]]] = []
    for position, line in enumerate(priced.lines):
        row = OrderLine(
            id=uuid.uuid4(),
            business_id=business_id,
            order_id=order.id,
            position=position,
            item_provenance_id=line.item_provenance_id,
            display_name=line.display_name,
            base_price_minor=line.base_price_minor,
            quantity=line.quantity,
            item_instructions=line.item_instructions,
            line_total_minor=line.line_total_minor,
        )
        repository.add(db, row)
        rows.append((row, line.options))
    # Lines before options (see the flush note in ``place_order``).
    db.flush()
    for row, options in rows:
        for option_position, option in enumerate(options):
            repository.add(
                db,
                OrderLineOption(
                    business_id=business_id,
                    line_id=row.id,
                    position=option_position,
                    group_provenance_id=option.group_provenance_id,
                    option_provenance_id=option.option_provenance_id,
                    group_display_name=option.group_display_name,
                    option_display_name=option.option_display_name,
                    price_delta_minor=option.price_delta_minor,
                ),
            )


def _order_by_token(db: Session, business: ResolvedBusiness, tracking_token: str) -> Order:
    """Token possession plus Host, both required (ruling D4).

    The token is compared only as its SHA-256 digest under the already
    host-resolved Business; a wrong token, a foreign business's token,
    and a malformed token are one neutral 404. Deliberately **not**
    entitlement-gated (D10 as amended in review): an order already
    placed stays trackable after the platform revokes ordering.
    """
    digest = hashlib.sha256(tracking_token.encode("utf-8")).hexdigest()
    order = repository.get_order_by_token_digest(
        db, business_id=business.business_id, digest=digest
    )
    if order is None:
        raise ResourceNotFoundError("Not found.")
    return order


def get_order_by_token(
    db: Session, business: ResolvedBusiness, tracking_token: str
) -> PublicOrderView:
    """The customer tracking projection (M6B) — stored snapshot only."""
    order = _order_by_token(db, business, tracking_token)
    return _order_view(db, business, order)


def cancel_by_token(
    db: Session, business: ResolvedBusiness, tracking_token: str
) -> PublicOrderView:
    """Customer cancellation (ruling D11): legal only from ``submitted``.

    Idempotent on a cancelled order (repeating the cancel returns the
    order unchanged — a double-tap is not an error); anything past
    ``submitted`` is M7's machine and refuses with ``invalid_state``.
    Runs under the Business row lock so the D3 slot count and a racing
    placement serialize against the release of this order's slot.
    """
    locked = businesses_repository.get_for_update(db, business.business_id)
    if locked is None or locked.status != BusinessStatus.ACTIVE.value:
        raise ResourceNotFoundError("Not found.")
    order = _order_by_token(db, business, tracking_token)
    if order.status == OrderStatus.CANCELLED.value:
        return _order_view(db, business, order)
    if order.status != OrderStatus.SUBMITTED.value:
        raise InvalidStateError("This order can no longer be cancelled online.")
    order.status = OrderStatus.CANCELLED.value
    repository.add(
        db,
        OrderStatusEvent(
            business_id=business.business_id,
            order_id=order.id,
            from_status=OrderStatus.SUBMITTED.value,
            to_status=OrderStatus.CANCELLED.value,
            actor_kind=StatusActorKind.CUSTOMER.value,
            actor_user_id=None,
        ),
    )
    recorder.record(
        db,
        AuditAction.ORDER_CANCELLED_BY_CUSTOMER,
        actor_user_id=None,
        business_id=business.business_id,
        target_type="order",
        target_id=str(order.id),
        details=OrderCancelledByCustomerDetails(order_number=order.order_number),
    )
    db.commit()
    return _order_view(db, business, order)


def list_pickup_slots(db: Session, business: ResolvedBusiness) -> PublicPickupSlots:
    """The bounded slot enumeration for the scheduled-pickup picker (M6B).

    Gated exactly like placement (ruling D10): no entitlement or no
    pickup is the one neutral 404. The bound is the shared
    ``MAX_PUBLIC_SLOTS`` policy, so what this lists and what checkout
    accepts are one set by construction.
    """
    _require_ordering_enabled(db, business)
    now = datetime.now(UTC)
    policy = effective_policy(db, business.business_id)
    weekly, exceptions, tz = _hours_inputs(db, business)
    return PublicPickupSlots(
        slots=pickup_slots(
            now,
            weekly=weekly,
            exceptions=exceptions,
            policy=policy,
            tz=tz,
            limit=policies.MAX_PUBLIC_SLOTS,
        )
    )


# --- The operational surface (M7A, ADR-027) ----------------------------------


def _authorize_operate(db: Session, actor: ActorContext, business_id: uuid.UUID) -> Business:
    """The D2 authority: reads AND commands under one named capability.

    The operational surface carries customer PII, so its authority is
    never inherited from ``business.view``; platform administrators hold
    no membership and get the same 404 as everywhere.
    """
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_ORDERS_OPERATE
    )
    business = businesses_repository.get(db, business_id)
    if business is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    return business


def _summary(order: Order) -> AdminOrderSummary:
    return AdminOrderSummary(
        id=order.id,
        order_number=order.order_number,
        status=OrderStatus(order.status),
        placed_at=order.placed_at,
        pickup_kind=PickupKind(order.pickup_kind),
        promised_pickup_at=order.promised_pickup_at,
        estimated_ready_at=order.estimated_ready_at,
        customer_name=order.customer_name,
        total_minor=order.total_minor,
        currency=order.currency,
    )


def list_orders_admin(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    *,
    statuses: list[OrderStatus] | None,
    placed_after: datetime | None,
    placed_before: datetime | None,
    q: str | None,
    before_number: int | None,
    limit: int,
) -> AdminOrderList:
    """One newest-first operational page (ruling D6)."""
    _authorize_operate(db, actor, business_id)
    rows = repository.list_orders(
        db,
        business_id=business_id,
        statuses=statuses,
        placed_after=placed_after,
        placed_before=placed_before,
        q=q,
        before_number=before_number,
        limit=limit,
    )
    return AdminOrderList(
        orders=[_summary(order) for order in rows],
        # A full page may end exactly at the last row; the next request
        # then answers empty — the honest end, the audit-stream shape.
        next_before_number=rows[-1].order_number if len(rows) == limit else None,
    )


def _detail(db: Session, business_id: uuid.UUID, order: Order) -> AdminOrderDetail:
    lines = repository.list_lines(db, business_id=business_id, order_id=order.id)
    options = repository.list_options_for_lines(
        db, business_id=business_id, line_ids=[line.id for line in lines]
    )
    events = repository.list_status_events(db, business_id=business_id, order_id=order.id)
    return AdminOrderDetail(
        id=order.id,
        order_number=order.order_number,
        status=OrderStatus(order.status),
        placed_at=order.placed_at,
        business_timezone=order.business_timezone,
        pickup_kind=PickupKind(order.pickup_kind),
        promised_pickup_at=order.promised_pickup_at,
        estimated_ready_at=order.estimated_ready_at,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        customer_email=order.customer_email,
        order_instructions=order.order_instructions,
        consent_updates=order.consent_updates,
        consent_marketing=order.consent_marketing,
        payment=policies.PAYMENT_DISPLAY,
        source=policies.SOURCE_DISPLAY,
        currency=order.currency,
        subtotal_minor=order.subtotal_minor,
        tax_minor=order.tax_minor,
        total_minor=order.total_minor,
        lines=[
            PublicOrderLine(
                display_name=line.display_name,
                quantity=line.quantity,
                base_price_minor=line.base_price_minor,
                options=[
                    PublicOrderLineOption(
                        group_name=option.group_display_name,
                        option_name=option.option_display_name,
                        price_delta_minor=option.price_delta_minor,
                    )
                    for option in options.get(line.id, [])
                ],
                line_total_minor=line.line_total_minor,
            )
            for line in lines
        ],
        timeline=[
            StatusEventView(
                from_status=None if event.from_status is None else OrderStatus(event.from_status),
                to_status=OrderStatus(event.to_status),
                actor_kind=event.actor_kind,
                occurred_at=event.occurred_at,
            )
            for event in events
        ],
    )


def get_order_admin(
    db: Session, actor: ActorContext, business_id: uuid.UUID, order_id: uuid.UUID
) -> AdminOrderDetail:
    """The full operational projection, timeline included (ruling D6)."""
    _authorize_operate(db, actor, business_id)
    order = repository.get_order(db, business_id=business_id, order_id=order_id)
    if order is None:
        raise ResourceNotFoundError("Order not found.")
    return _detail(db, business_id, order)


_TRANSITION_AUDIT: dict[str, AuditAction] = {
    "accept": AuditAction.ORDER_ACCEPTED,
    "reject": AuditAction.ORDER_REJECTED,
    "start-preparing": AuditAction.ORDER_PREPARING,
    "mark-ready": AuditAction.ORDER_READY,
    "complete": AuditAction.ORDER_COMPLETED,
    "cancel": AuditAction.ORDER_CANCELLED_BY_MEMBER,
}


def transition_order(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    command: str,
) -> AdminOrderDetail:
    """One named member command (rulings D1/D3/D4).

    The order row is locked and its state re-read inside the
    transaction; an illegal current state answers ``409 invalid_state``
    with the current status in the typed details — the losing device of
    a race refetches and shows the truth. The slot-releasing commands
    (reject, cancel) additionally take the Business lock FIRST, the
    D11-M6 precedent: release serializes with a racing placement's
    count. Lock order is therefore always Business → order, acyclic
    with every other orders transaction.
    """
    legal_from, target = MEMBER_TRANSITIONS[command]
    _authorize_operate(db, actor, business_id)
    if target in SLOT_RELEASING_STATUSES:
        locked = businesses_repository.get_for_update(db, business_id)
        if locked is None:  # pragma: no cover - membership implies existence
            raise ResourceNotFoundError("Business not found.")
    order = repository.get_order_for_update(db, business_id=business_id, order_id=order_id)
    if order is None:
        raise ResourceNotFoundError("Order not found.")
    if order.status != legal_from.value:
        raise ApiError(
            409,
            ErrorCode.INVALID_STATE,
            f"This order cannot be {_COMMAND_VERBS[command]} from its current state.",
            details={"status": order.status},
        )
    order.status = target.value
    repository.add(
        db,
        OrderStatusEvent(
            business_id=business_id,
            order_id=order.id,
            from_status=legal_from.value,
            to_status=target.value,
            actor_kind=StatusActorKind.MEMBER.value,
            actor_user_id=actor.user.id,
        ),
    )
    recorder.record(
        db,
        _TRANSITION_AUDIT[command],
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="order",
        target_id=str(order.id),
        details=OrderTransitionDetails(
            order_number=order.order_number,
            from_status=legal_from.value,
            to_status=target.value,
        ),
    )
    db.commit()
    return _detail(db, business_id, order)


_COMMAND_VERBS: dict[str, str] = {
    "accept": "accepted",
    "reject": "rejected",
    "start-preparing": "moved to preparing",
    "mark-ready": "marked ready",
    "complete": "completed",
    "cancel": "cancelled",
}


def set_estimate(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: OrderEstimateSet,
) -> AdminOrderDetail:
    """Set or clear the prep estimate (ruling D7).

    Legal only while the kitchen owns the order (accepted/preparing);
    audited, never evented — the timeline stays the status trail.
    """
    _authorize_operate(db, actor, business_id)
    order = repository.get_order_for_update(db, business_id=business_id, order_id=order_id)
    if order is None:
        raise ResourceNotFoundError("Order not found.")
    if OrderStatus(order.status) not in ESTIMATE_LEGAL_STATUSES:
        raise ApiError(
            409,
            ErrorCode.INVALID_STATE,
            "An estimate can be set only while the order is accepted or preparing.",
            details={"status": order.status},
        )
    if order.estimated_ready_at == payload.estimated_ready_at:
        return _detail(db, business_id, order)
    order.estimated_ready_at = payload.estimated_ready_at
    recorder.record(
        db,
        AuditAction.ORDER_ESTIMATE_SET,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="order",
        target_id=str(order.id),
        details=OrderEstimateSetDetails(
            order_number=order.order_number,
            estimate="cleared" if payload.estimated_ready_at is None else "set",
            estimated_ready_at=(
                None
                if payload.estimated_ready_at is None
                else payload.estimated_ready_at.isoformat()
            ),
        ),
    )
    db.commit()
    return _detail(db, business_id, order)


def order_metrics(db: Session, actor: ActorContext, business_id: uuid.UUID) -> OrderMetrics:
    """Today's operational metrics (ruling D11) — computed, never stored.

    "Today" is the tenant-local calendar day, converted to a UTC window;
    every aggregate is arithmetic over that window's orders, their
    snapshot lines, and their status events.
    """
    business = _authorize_operate(db, actor, business_id)
    now = datetime.now(UTC)
    tz = ZoneInfo(business.timezone)
    day = local_date(now, tz)
    since = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    until = since + timedelta(days=1)
    orders = repository.metrics_orders(db, business_id=business_id, since=since, until=until)
    standing = [
        order for order in orders if OrderStatus(order.status) not in SLOT_RELEASING_STATUSES
    ]
    sales = sum(order.total_minor for order in standing)
    order_ids = [order.id for order in orders]
    quantities: dict[str, int] = {}
    for line in repository.lines_for_orders(db, business_id=business_id, order_ids=order_ids):
        quantities[line.display_name] = quantities.get(line.display_name, 0) + line.quantity
    popular = sorted(quantities.items(), key=lambda item: (-item[1], item[0]))
    accepted_at: dict[uuid.UUID, datetime] = {}
    ready_at: dict[uuid.UUID, datetime] = {}
    for event in repository.events_for_orders(db, business_id=business_id, order_ids=order_ids):
        if event.to_status == OrderStatus.ACCEPTED.value:
            accepted_at[event.order_id] = event.occurred_at
        elif event.to_status == OrderStatus.READY.value:
            ready_at[event.order_id] = event.occurred_at
    prep_seconds = [
        (ready_at[order_id] - accepted_at[order_id]).total_seconds()
        for order_id in ready_at
        if order_id in accepted_at
    ]
    return OrderMetrics(
        day=day.isoformat(),
        timezone=business.timezone,
        order_count=len(orders),
        standing_order_count=len(standing),
        sales_minor=sales,
        average_order_value_minor=(sales // len(standing)) if standing else None,
        cancelled_count=sum(1 for order in orders if order.status == OrderStatus.CANCELLED.value),
        rejected_count=sum(1 for order in orders if order.status == OrderStatus.REJECTED.value),
        popular_items=[
            PopularItem(display_name=name, quantity=quantity)
            for name, quantity in popular[: policies.METRICS_POPULAR_ITEMS]
        ],
        average_prep_seconds=(int(sum(prep_seconds) / len(prep_seconds)) if prep_seconds else None),
    )


def _replay(
    db: Session, business: ResolvedBusiness, existing: IdempotencyKey, digest: str
) -> OrderPlacedResponse:
    """An honest retry returns the stored order; key reuse is a typed 409.

    The replayed body carries the order's **current** representation
    (review amendment — a cancellation between attempts shows honestly)
    and an empty ``tracking_token``: the token is disclosed exactly once.
    """
    if existing.request_digest != digest:
        raise ApiError(
            409,
            ErrorCode.IDEMPOTENCY_KEY_REUSED,
            "This idempotency key was already used for a different order.",
        )
    if existing.order_id is None:  # pragma: no cover - placement always links
        raise ResourceNotFoundError("Not found.")
    order = repository.get_order(db, business_id=business.business_id, order_id=existing.order_id)
    if order is None:  # pragma: no cover - composite FK keeps these together
        raise ResourceNotFoundError("Not found.")
    return OrderPlacedResponse(tracking_token="", order=_order_view(db, business, order))
