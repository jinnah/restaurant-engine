"""Hours API schemas (M5A, ADR-025).

Command schemas reject unknown fields (blueprint §11.3); responses are
explicit, never serialized ORM objects. Interval values use the D1 minute
encoding end to end — the control center converts to and from time
pickers, the API stores exactly what the domain computes with.

The two write commands are **full-set replacements** (the storefront-draft
and entitlement precedent): the weekly PUT carries the whole week, the
per-date exception PUT carries that date's whole override. Overlap
validation is therefore a pure function of the payload, enforced here,
before any database work.
"""

from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.hours import policies
from app.domains.hours.availability import (
    WeeklyInterval as DomainWeeklyInterval,
)
from app.domains.hours.availability import (
    find_day_overlap,
    find_weekly_overlap,
)

_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class HoursInterval(BaseModel):
    """One open interval in D1 minutes (0-1439 opens; closes may run to
    2879, ending on the following local day)."""

    model_config = ConfigDict(extra="forbid")

    opens_minute: int = Field(ge=policies.MIN_OPENS_MINUTE, le=policies.MAX_OPENS_MINUTE)
    closes_minute: int = Field(ge=policies.MIN_CLOSES_MINUTE, le=policies.MAX_CLOSES_MINUTE)

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if self.closes_minute <= self.opens_minute:
            msg = "closes_minute must be after opens_minute"
            raise ValueError(msg)
        if self.closes_minute - self.opens_minute > policies.MAX_INTERVAL_MINUTES:
            msg = "an interval may not exceed 24 hours"
            raise ValueError(msg)
        return self


class WeeklyIntervalIn(HoursInterval):
    """One weekly interval: ISO day (0 = Monday) plus the open interval."""

    day_of_week: int = Field(ge=0, le=6)


class WeeklyScheduleSet(BaseModel):
    """The complete desired weekly schedule (idempotent full replacement).

    An empty list is a valid schedule: never open. Per-day counts and
    week-circle non-overlap (an overnight interval is checked against the
    following day's openings) are validated here, so the service receives
    a set that is internally consistent by construction.
    """

    model_config = ConfigDict(extra="forbid")

    intervals: list[WeeklyIntervalIn] = Field(max_length=policies.MAX_WEEKLY_INTERVALS)

    @field_validator("intervals")
    @classmethod
    def _consistent(cls, value: list[WeeklyIntervalIn]) -> list[WeeklyIntervalIn]:
        per_day: dict[int, int] = {}
        for interval in value:
            per_day[interval.day_of_week] = per_day.get(interval.day_of_week, 0) + 1
        for day, count in per_day.items():
            if count > policies.MAX_INTERVALS_PER_DAY:
                msg = (
                    f"{_DAY_NAMES[day]} has {count} intervals; the limit is "
                    f"{policies.MAX_INTERVALS_PER_DAY} per day"
                )
                raise ValueError(msg)
        domain = [
            DomainWeeklyInterval(i.day_of_week, i.opens_minute, i.closes_minute) for i in value
        ]
        overlap = find_weekly_overlap(domain)
        if overlap is not None:
            first, second = overlap
            msg = (
                f"intervals overlap: {_DAY_NAMES[first.day_of_week]} "
                f"{first.opens_minute}-{first.closes_minute} and "
                f"{_DAY_NAMES[second.day_of_week]} "
                f"{second.opens_minute}-{second.closes_minute}"
            )
            raise ValueError(msg)
        # Canonical order (day, opens): equality against the stored set is
        # then a list comparison, which is what makes the exact no-op
        # suppression in the service trivial and reviewable.
        return sorted(value, key=lambda i: (i.day_of_week, i.opens_minute, i.closes_minute))


class ScheduleExceptionSet(BaseModel):
    """One date's complete override: special hours, or closed all day.

    ``intervals: []`` means **closed all day** — removing the exception
    entirely is the DELETE route, so absence and closure stay distinct
    intents. ``note`` is the D6 label (bounded plain text, normalized,
    control characters rejected).
    """

    model_config = ConfigDict(extra="forbid")

    intervals: list[HoursInterval] = Field(
        default_factory=list, max_length=policies.MAX_INTERVALS_PER_DAY
    )
    note: str | None = Field(default=None, max_length=policies.MAX_NOTE_LENGTH * 4)

    @field_validator("intervals")
    @classmethod
    def _non_overlapping(cls, value: list[HoursInterval]) -> list[HoursInterval]:
        overlap = find_day_overlap([(i.opens_minute, i.closes_minute) for i in value])
        if overlap is not None:
            (opens_a, closes_a), (opens_b, closes_b) = overlap
            msg = f"intervals overlap: {opens_a}-{closes_a} and {opens_b}-{closes_b}"
            raise ValueError(msg)
        return sorted(value, key=lambda i: (i.opens_minute, i.closes_minute))

    @field_validator("note")
    @classmethod
    def _normalized_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if policies.has_control_characters(value):
            msg = "must not contain control characters"
            raise ValueError(msg)
        normalized = policies.normalize_note(value)
        if not normalized:
            return None
        if len(normalized) > policies.MAX_NOTE_LENGTH:
            msg = f"must be at most {policies.MAX_NOTE_LENGTH} characters"
            raise ValueError(msg)
        return normalized


class FulfillmentSet(BaseModel):
    """The complete desired fulfillment policy (full-document, idempotent).

    Every M5A field is required: partial updates would reintroduce the
    lost-update shape the full-document convention exists to avoid.
    ``max_orders_per_slot`` (M6A, ADR-026 D3) is additive with a default
    — the M4G-A compatibility mechanism: a document from a client
    predating the field (the delivered M5C form, until M6D adds its
    control) omits it, and omission is the null it defaults to, which
    means unlimited. Nothing stored is silently changed by an old
    client's save, because null is exactly what every row holds today.
    """

    model_config = ConfigDict(extra="forbid")

    pickup_enabled: bool
    asap_enabled: bool
    lead_time_minutes: int = Field(
        ge=policies.MIN_LEAD_TIME_MINUTES, le=policies.MAX_LEAD_TIME_MINUTES
    )
    slot_interval_minutes: int = Field(
        ge=policies.MIN_SLOT_INTERVAL_MINUTES, le=policies.MAX_SLOT_INTERVAL_MINUTES
    )
    last_order_before_close_minutes: int = Field(
        ge=policies.MIN_LAST_ORDER_MINUTES, le=policies.MAX_LAST_ORDER_MINUTES
    )
    max_days_ahead: int = Field(ge=policies.MIN_MAX_DAYS_AHEAD, le=policies.MAX_MAX_DAYS_AHEAD)
    max_orders_per_slot: int | None = Field(
        default=None,
        ge=policies.MIN_MAX_ORDERS_PER_SLOT,
        le=policies.MAX_MAX_ORDERS_PER_SLOT,
    )


class WeeklyIntervalOut(BaseModel):
    day_of_week: int
    opens_minute: int
    closes_minute: int


class ScheduleExceptionOut(BaseModel):
    """One date's stored override. ``intervals`` empty = closed all day."""

    exception_date: date
    intervals: list[HoursInterval]
    note: str | None


class FulfillmentOut(BaseModel):
    """The effective policy — the stored row, or the documented defaults.

    ``is_configured`` says which, so the UI can present "using defaults"
    honestly without comparing values against a copy of the registry.
    The pause facts (M7A, ADR-027 D8) are read here but written only by
    their own command — ``ordering_paused`` is the STORED flag; whether
    it is currently effective is computed against the resume instant.
    """

    pickup_enabled: bool
    asap_enabled: bool
    lead_time_minutes: int
    slot_interval_minutes: int
    last_order_before_close_minutes: int
    max_days_ahead: int
    max_orders_per_slot: int | None
    ordering_paused: bool
    pause_note: str | None
    pause_resume_at: datetime | None
    is_configured: bool


class OrderingPauseSet(BaseModel):
    """The pause/resume command body (M7A, ADR-027 ruling D8).

    Its own command, never a fulfillment-document field (the review
    amendment: a full-document save from an older client must not
    silently unpause a business). Resuming clears the note and instant;
    a note or resume instant without ``paused`` is a contradiction and
    is refused. The note is customer-visible bounded plain text, the D6
    exception-note policy applied verbatim.
    """

    model_config = ConfigDict(extra="forbid")

    paused: bool
    note: str | None = Field(default=None, max_length=policies.MAX_NOTE_LENGTH * 4)
    resume_at: datetime | None = None

    @field_validator("note")
    @classmethod
    def _normalized_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if policies.has_control_characters(value):
            msg = "must not contain control characters"
            raise ValueError(msg)
        normalized = policies.normalize_note(value)
        if not normalized:
            return None
        if len(normalized) > policies.MAX_NOTE_LENGTH:
            msg = f"must be at most {policies.MAX_NOTE_LENGTH} characters"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if not self.paused and (self.note is not None or self.resume_at is not None):
            msg = "a note or resume time requires paused to be true"
            raise ValueError(msg)
        return self


class HoursSettings(BaseModel):
    """The complete operating configuration in one read.

    ``timezone`` is the business's IANA zone — stated here because every
    minute value below is local wall time under exactly that zone.
    Exceptions are the bounded window around today (tenant-local), sorted
    by date.
    """

    timezone: str
    weekly: list[WeeklyIntervalOut]
    exceptions: list[ScheduleExceptionOut]
    fulfillment: FulfillmentOut


class AvailabilityPreview(BaseModel):
    """The authenticated probe's answer: the computed facts at ``at``.

    The same shape the public projection derives from (M5B), computed for
    members at an arbitrary instant so a DST weekend or a holiday can be
    checked before it happens — and so the E2E suite can exercise
    transitions deterministically.
    """

    at: datetime
    timezone: str
    is_open_now: bool
    closes_at: datetime | None
    next_opens_at: datetime | None
    next_pickup_at: datetime | None


class HoursDeletedResponse(BaseModel):
    """Acknowledgement for the exception DELETE."""

    status: str = "deleted"
