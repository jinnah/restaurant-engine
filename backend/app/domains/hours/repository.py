"""Tenant-safe hours data access (M5A, ADR-025).

Repositories never commit (M2A discipline): the hours service owns the
transaction. Every method requires ``business_id`` — a signature that can
read tenant-owned rows without one is invalid by §3.1.
"""

import uuid
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domains.hours.models import BusinessHours, FulfillmentSettings, ScheduleException


def list_weekly(db: Session, *, business_id: uuid.UUID) -> list[BusinessHours]:
    """The stored weekly schedule in canonical (day, opens) order."""
    return list(
        db.execute(
            select(BusinessHours)
            .where(BusinessHours.business_id == business_id)
            .order_by(
                BusinessHours.day_of_week,
                BusinessHours.opens_minute,
                BusinessHours.closes_minute,
            )
        ).scalars()
    )


def replace_weekly(
    db: Session, *, business_id: uuid.UUID, intervals: list[tuple[int, int, int]]
) -> None:
    """Replace the whole weekly schedule (delete + insert, one transaction).

    Runs only under the service's Business row lock, which serializes
    concurrent replacements; the submitted set was validated as a pure
    function before this is called.
    """
    db.execute(delete(BusinessHours).where(BusinessHours.business_id == business_id))
    for day_of_week, opens_minute, closes_minute in intervals:
        db.add(
            BusinessHours(
                business_id=business_id,
                day_of_week=day_of_week,
                opens_minute=opens_minute,
                closes_minute=closes_minute,
            )
        )


def list_exceptions(
    db: Session, *, business_id: uuid.UUID, start: date, end: date
) -> list[ScheduleException]:
    """Exception rows with ``start <= exception_date <= end``, date-ordered."""
    return list(
        db.execute(
            select(ScheduleException)
            .where(
                ScheduleException.business_id == business_id,
                ScheduleException.exception_date >= start,
                ScheduleException.exception_date <= end,
            )
            .order_by(
                ScheduleException.exception_date,
                ScheduleException.opens_minute.nulls_first(),
            )
        ).scalars()
    )


def list_exception_rows_for_date(
    db: Session, *, business_id: uuid.UUID, exception_date: date
) -> list[ScheduleException]:
    return list(
        db.execute(
            select(ScheduleException)
            .where(
                ScheduleException.business_id == business_id,
                ScheduleException.exception_date == exception_date,
            )
            .order_by(ScheduleException.opens_minute.nulls_first())
        ).scalars()
    )


def replace_exception(
    db: Session,
    *,
    business_id: uuid.UUID,
    exception_date: date,
    intervals: list[tuple[int, int]],
    note: str | None,
) -> None:
    """Replace one date's override rows exactly (delete + insert).

    An empty ``intervals`` list stores the single closed-all-day row (NULL
    interval). The note is stored on every row of the date so the date's
    override remains one self-contained set.
    """
    db.execute(
        delete(ScheduleException).where(
            ScheduleException.business_id == business_id,
            ScheduleException.exception_date == exception_date,
        )
    )
    if not intervals:
        db.add(
            ScheduleException(
                business_id=business_id,
                exception_date=exception_date,
                opens_minute=None,
                closes_minute=None,
                note=note,
            )
        )
        return
    for opens_minute, closes_minute in intervals:
        db.add(
            ScheduleException(
                business_id=business_id,
                exception_date=exception_date,
                opens_minute=opens_minute,
                closes_minute=closes_minute,
                note=note,
            )
        )


def delete_exception(db: Session, *, business_id: uuid.UUID, exception_date: date) -> int:
    """Remove one date's override rows; returns how many rows existed.

    The count comes from a scalar SELECT under the caller's business row
    lock rather than ``rowcount``, which SQLAlchemy types as
    driver-optional on a bare ``Result``.
    """
    existing = db.execute(
        select(func.count())
        .select_from(ScheduleException)
        .where(
            ScheduleException.business_id == business_id,
            ScheduleException.exception_date == exception_date,
        )
    ).scalar_one()
    if existing:
        db.execute(
            delete(ScheduleException).where(
                ScheduleException.business_id == business_id,
                ScheduleException.exception_date == exception_date,
            )
        )
    return int(existing)


def get_fulfillment(db: Session, *, business_id: uuid.UUID) -> FulfillmentSettings | None:
    return db.execute(
        select(FulfillmentSettings).where(FulfillmentSettings.business_id == business_id)
    ).scalar_one_or_none()


def add(db: Session, entity: FulfillmentSettings) -> None:
    db.add(entity)
