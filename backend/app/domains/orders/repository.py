"""Tenant-safe orders data access (M6A, ADR-026).

Every read of tenant-owned data takes ``business_id`` (docs/04). The
repository never commits (blueprint §14.1); the service owns the one
placement transaction.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domains.orders.lifecycle import OrderStatus
from app.domains.orders.models import IdempotencyKey, Order, OrderLine, OrderLineOption


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
    """Non-cancelled orders promised for exactly this slot instant (D3)."""
    return db.execute(
        select(func.count())
        .select_from(Order)
        .where(
            Order.business_id == business_id,
            Order.promised_pickup_at == promised_pickup_at,
            Order.status != OrderStatus.CANCELLED.value,
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
