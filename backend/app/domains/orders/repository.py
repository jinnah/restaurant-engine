"""Tenant-safe orders data access (M6A, ADR-026).

Every read of tenant-owned data takes ``business_id`` (docs/04). The
repository never commits (blueprint §14.1); the service owns the one
placement transaction.
"""

import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domains.orders.lifecycle import SLOT_RELEASING_STATUSES, OrderStatus
from app.domains.orders.models import (
    IdempotencyKey,
    Order,
    OrderLine,
    OrderLineOption,
    OrderStatusEvent,
)


def add(db: Session, instance: Base) -> None:
    db.add(instance)


def next_order_number(db: Session, *, business_id: uuid.UUID) -> int:
    """The next tenant-scoped order number (ruling D5).

    ``MAX + 1`` is race-free only under the Business row lock the
    placement transaction already holds; orders are never deleted, so
    the sequence is dense from 1.
    """
    current = db.execute(
        select(func.max(Order.order_number)).where(Order.business_id == business_id)
    ).scalar_one()
    return 1 if current is None else current + 1


def count_orders_for_slot(
    db: Session, *, business_id: uuid.UUID, promised_pickup_at: datetime
) -> int:
    """Orders occupying exactly this slot instant (D3, amended D3-M7).

    Cancelled AND rejected orders release their slot (ADR-027 D3): a
    refused order occupies no kitchen capacity. The releasing commands
    run under the Business lock so this count and a racing placement
    serialize.
    """
    return db.execute(
        select(func.count())
        .select_from(Order)
        .where(
            Order.business_id == business_id,
            Order.promised_pickup_at == promised_pickup_at,
            Order.status.notin_([status.value for status in SLOT_RELEASING_STATUSES]),
        )
    ).scalar_one()


def get_order(db: Session, *, business_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    return db.execute(
        select(Order).where(Order.business_id == business_id, Order.id == order_id)
    ).scalar_one_or_none()


def get_order_by_token_digest(db: Session, *, business_id: uuid.UUID, digest: str) -> Order | None:
    """Token possession plus Host, both required (ruling D4)."""
    return db.execute(
        select(Order).where(
            Order.business_id == business_id,
            Order.tracking_token_digest == digest,
        )
    ).scalar_one_or_none()


def list_lines(db: Session, *, business_id: uuid.UUID, order_id: uuid.UUID) -> list[OrderLine]:
    return list(
        db.execute(
            select(OrderLine)
            .where(OrderLine.business_id == business_id, OrderLine.order_id == order_id)
            .order_by(OrderLine.position)
        )
        .scalars()
        .all()
    )


def list_options_for_lines(
    db: Session, *, business_id: uuid.UUID, line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[OrderLineOption]]:
    if not line_ids:
        return {}
    rows = db.execute(
        select(OrderLineOption)
        .where(
            OrderLineOption.business_id == business_id,
            OrderLineOption.line_id.in_(line_ids),
        )
        .order_by(OrderLineOption.position)
    )
    result: dict[uuid.UUID, list[OrderLineOption]] = {}
    for option in rows.scalars().all():
        result.setdefault(option.line_id, []).append(option)
    return result


def get_idempotency(
    db: Session, *, business_id: uuid.UUID, operation: str, idempotency_key: uuid.UUID
) -> IdempotencyKey | None:
    return db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.business_id == business_id,
            IdempotencyKey.operation == operation,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()


# --- The operational surface (M7A, ADR-027) ----------------------------------


def get_order_for_update(
    db: Session, *, business_id: uuid.UUID, order_id: uuid.UUID
) -> Order | None:
    """The order row, locked (ruling D1): transitions serialize here."""
    return db.execute(
        select(Order)
        .where(Order.business_id == business_id, Order.id == order_id)
        .with_for_update()
    ).scalar_one_or_none()


def _apply_list_filters(
    statement: Select[tuple[Order]],
    *,
    statuses: list[OrderStatus] | None,
    placed_after: datetime | None,
    placed_before: datetime | None,
    q: str | None,
) -> Select[tuple[Order]]:
    if statuses:
        statement = statement.where(Order.status.in_([status.value for status in statuses]))
    if placed_after is not None:
        statement = statement.where(Order.placed_at >= placed_after)
    if placed_before is not None:
        statement = statement.where(Order.placed_at < placed_before)
    if q is not None:
        if q.isdigit():
            statement = statement.where(Order.order_number == int(q))
        else:
            # Case-insensitive prefix over the customer facts (ruling D6);
            # this same filter is "customer-linked order history".
            prefix = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"{prefix}%"
            statement = statement.where(
                or_(
                    Order.customer_name.ilike(pattern),
                    Order.customer_phone.ilike(pattern),
                    Order.customer_email.ilike(pattern),
                )
            )
    return statement


def list_orders(
    db: Session,
    *,
    business_id: uuid.UUID,
    statuses: list[OrderStatus] | None,
    placed_after: datetime | None,
    placed_before: datetime | None,
    q: str | None,
    before_number: int | None,
    limit: int,
) -> list[Order]:
    """Newest-first operational page (ruling D6 as amended in delivery).

    The cursor is the dense, tenant-scoped ``order_number`` — monotonic
    by construction (allocated under the Business lock), served by the
    existing ``(business_id, order_number)`` unique, and exclusive like
    the ADR-014 audit cursor. (Order ids are random UUID4: an id cursor
    would not be a time cursor — the delivery correction to the ADR's
    UUIDv7 assumption.)
    """
    statement = select(Order).where(Order.business_id == business_id)
    statement = _apply_list_filters(
        statement,
        statuses=statuses,
        placed_after=placed_after,
        placed_before=placed_before,
        q=q,
    )
    if before_number is not None:
        # Exclusive cursor, the audit-pagination shape.
        statement = statement.where(Order.order_number < before_number)
    return list(
        db.execute(statement.order_by(Order.order_number.desc()).limit(limit)).scalars().all()
    )


def list_status_events(
    db: Session, *, business_id: uuid.UUID, order_id: uuid.UUID
) -> list[OrderStatusEvent]:
    """The append-only timeline, oldest first (ruling D7: events only)."""
    return list(
        db.execute(
            select(OrderStatusEvent)
            .where(
                OrderStatusEvent.business_id == business_id,
                OrderStatusEvent.order_id == order_id,
            )
            .order_by(OrderStatusEvent.occurred_at, OrderStatusEvent.id)
        )
        .scalars()
        .all()
    )


def metrics_orders(
    db: Session, *, business_id: uuid.UUID, since: datetime, until: datetime
) -> list[Order]:
    """Today's orders for the D11 metrics read — computed, never stored.

    Pilot-scale by design: one bounded window of one tenant's orders,
    aggregated in the service where the arithmetic stays testable.
    """
    return list(
        db.execute(
            select(Order).where(
                Order.business_id == business_id,
                Order.placed_at >= since,
                Order.placed_at < until,
            )
        )
        .scalars()
        .all()
    )


def lines_for_orders(
    db: Session, *, business_id: uuid.UUID, order_ids: list[uuid.UUID]
) -> list[OrderLine]:
    if not order_ids:
        return []
    return list(
        db.execute(
            select(OrderLine).where(
                OrderLine.business_id == business_id,
                OrderLine.order_id.in_(order_ids),
            )
        )
        .scalars()
        .all()
    )


def events_for_orders(
    db: Session, *, business_id: uuid.UUID, order_ids: list[uuid.UUID]
) -> list[OrderStatusEvent]:
    if not order_ids:
        return []
    return list(
        db.execute(
            select(OrderStatusEvent).where(
                OrderStatusEvent.business_id == business_id,
                OrderStatusEvent.order_id.in_(order_ids),
            )
        )
        .scalars()
        .all()
    )
