"""Hours persistence models (M5A, ADR-025).

Hours owns the three blueprint §9 operations tables: ``business_hours``
(the recurring weekly schedule), ``schedule_exceptions`` (date-specific
overrides), and ``fulfillment_settings`` (the per-business pickup policy).
All three are tenant-owned: ``business_id`` leads every index (§8.2).

Times are stored as **local wall minutes** under ruling D1 — the tenant's
IANA timezone (``businesses.timezone``) is the only bridge to instants,
applied in ``hours.timekeeping`` at computation time, never at rest. A
CHECK bounds each minute value; interval *non-overlap* is validated by the
service as a pure function of the submitted full set (a database EXCLUDE
would need the btree_gist extension — recorded as a hardening candidate,
not adopted).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BusinessHours(Base):
    """One recurring weekly open interval (D1 minute encoding).

    ``day_of_week`` is ISO: 0 = Monday … 6 = Sunday, matching
    ``datetime.date.weekday()`` so no translation layer can drift.
    ``closes_minute`` above 1440 ends the interval on the following local
    day; the pair of CHECKs bounds the values and caps one interval at 24
    hours, so the week-circle arithmetic in ``hours.availability`` is
    total.
    """

    __tablename__ = "business_hours"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    closes_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="day_of_week_valid"),
        CheckConstraint("opens_minute BETWEEN 0 AND 1439", name="opens_minute_bounds"),
        CheckConstraint("closes_minute BETWEEN 1 AND 2879", name="closes_minute_bounds"),
        CheckConstraint("closes_minute > opens_minute", name="closes_after_opens"),
        CheckConstraint("closes_minute - opens_minute <= 1440", name="interval_at_most_one_day"),
        # The weekly read path and the full-week replacement's delete.
        Index("ix_business_hours_business_id_day", "business_id", "day_of_week"),
    )


class ScheduleException(Base):
    """One date-specific override row (M5A, ADR-025).

    Any exception row for a local calendar date fully replaces the weekly
    schedule for that date. A NULL interval pair means **closed all day**
    (the partial unique index allows at most one such row per date); rows
    with intervals are that date's special hours. The service writes each
    date as one exact replacement set, so a closed row and interval rows
    can never coexist through the product; the pairing CHECK is the
    database's own guarantee that half an interval cannot be stored.

    ``exception_date`` is a **local calendar date in the tenant timezone**
    — never a UTC date (ADR-025 rule 6). ``note`` is the D6 label:
    bounded plain text explaining the exception, never freeform hours.
    """

    __tablename__ = "schedule_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    exception_date: Mapped[date] = mapped_column(Date, nullable=False)
    opens_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closes_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "(opens_minute IS NULL) = (closes_minute IS NULL)",
            name="interval_pairing",
        ),
        CheckConstraint(
            "opens_minute IS NULL OR opens_minute BETWEEN 0 AND 1439",
            name="opens_minute_bounds",
        ),
        CheckConstraint(
            "closes_minute IS NULL OR closes_minute BETWEEN 1 AND 2879",
            name="closes_minute_bounds",
        ),
        CheckConstraint(
            "closes_minute IS NULL OR closes_minute > opens_minute",
            name="closes_after_opens",
        ),
        CheckConstraint(
            "closes_minute IS NULL OR closes_minute - opens_minute <= 1440",
            name="interval_at_most_one_day",
        ),
        CheckConstraint(
            "note IS NULL OR char_length(note) BETWEEN 1 AND 120",
            name="note_length",
        ),
        # At most one closed-all-day row per business and date; interval
        # rows are unbounded within the per-date service limit.
        Index(
            "uq_schedule_exceptions_one_closed_per_date",
            "business_id",
            "exception_date",
            unique=True,
            postgresql_where=text("opens_minute IS NULL"),
        ),
        # The windowed read and the per-date replacement.
        Index("ix_schedule_exceptions_business_id_date", "business_id", "exception_date"),
    )


class FulfillmentSettings(Base):
    """The per-business fulfillment policy — at most one row (M5A).

    **No row means the documented defaults** (``hours.policies``),
    projected on read and materialized on the first write — the M4G-A
    compatibility mechanism, so no backfill migration touches existing
    tenants. ``max_orders_per_slot`` discharges the D3 deferral (M6A,
    ADR-026): hours owns the throttling *setting* per the docs/03 domain
    map; the orders checkout owns counting and enforcement. NULL means
    unlimited — existing rows gain no cap.
    """

    __tablename__ = "fulfillment_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    asap_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    lead_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    last_order_before_close_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_days_ahead: Mapped[int] = mapped_column(Integer, nullable=False)
    max_orders_per_slot: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("lead_time_minutes BETWEEN 0 AND 1440", name="lead_time_bounds"),
        CheckConstraint("slot_interval_minutes BETWEEN 5 AND 120", name="slot_interval_bounds"),
        CheckConstraint(
            "last_order_before_close_minutes BETWEEN 0 AND 240",
            name="last_order_bounds",
        ),
        CheckConstraint("max_days_ahead BETWEEN 0 AND 30", name="max_days_ahead_bounds"),
        CheckConstraint(
            "max_orders_per_slot IS NULL OR max_orders_per_slot BETWEEN 1 AND 100",
            name="max_orders_per_slot_bounds",
        ),
        CheckConstraint("updated_at >= created_at", name="updated_after_creation"),
    )
