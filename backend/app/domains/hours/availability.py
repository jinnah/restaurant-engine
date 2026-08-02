"""Pure availability and pickup-slot computation (M5A, ADR-025).

Everything here is a function of its arguments: the weekly schedule, the
exceptions, the fulfillment policy, the tenant timezone, and an injected
``now``. No database, no ambient clock — the composition order is the
contract, because precedence is where hours systems go wrong:

1. resolve the tenant-local date for ``now``;
2. an exception for a date **replaces** the weekly schedule for that date,
   entirely (empty intervals = closed all day);
3. intervals become instants under the ``timekeeping`` rules (an interval
   that collapses inside a DST gap contributes nothing);
4. openness is instant containment, never wall-clock comparison;
5. an overnight interval belongs to the local date whose schedule created
   it — Monday 17:00-02:00 still runs to 2 a.m. Tuesday when Tuesday
   carries a closed-all-day exception, because it is Monday's service;
6. pickup slots step in real time from each interval's opening, valid from
   ``now + lead_time`` through ``closes_at - last_order_before_close``,
   bounded by ``max_days_ahead`` counted in **service days**;
7. every scan is bounded, so a business with no hours terminates with
   "none" rather than looping.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from math import ceil
from zoneinfo import ZoneInfo

from app.domains.hours.policies import NEXT_OPENING_SCAN_DAYS
from app.domains.hours.timekeeping import local_date, wall_to_instant


@dataclass(frozen=True)
class WeeklyInterval:
    """One recurring open interval (D1 minute encoding; Monday = 0)."""

    day_of_week: int
    opens_minute: int
    closes_minute: int


@dataclass(frozen=True)
class ExceptionDay:
    """One date's complete override: its intervals, or closed all day."""

    exception_date: date
    intervals: tuple[tuple[int, int], ...]  # empty = closed all day
    note: str | None = None


@dataclass(frozen=True)
class FulfillmentPolicy:
    """The effective fulfillment settings (stored row or the defaults)."""

    pickup_enabled: bool
    asap_enabled: bool
    lead_time_minutes: int
    slot_interval_minutes: int
    last_order_before_close_minutes: int
    max_days_ahead: int
    # M6A (ADR-026 D3): the per-slot order cap; None = unlimited. Carried
    # on the effective policy so checkout reads one object, but never used
    # by the pure availability computations in this module.
    max_orders_per_slot: int | None = None


@dataclass(frozen=True)
class OpenInterval:
    """One realized open interval as UTC instants."""

    opens_at: datetime
    closes_at: datetime


@dataclass(frozen=True)
class AvailabilityFacts:
    """The instant answers the projections and preview expose."""

    is_open_now: bool
    closes_at: datetime | None  # when open: when the current interval ends
    next_opens_at: datetime | None  # when closed: the next opening instant
    next_pickup_at: datetime | None  # earliest valid pickup, when enabled


Schedule = Mapping[int, Sequence[tuple[int, int]]]
Exceptions = Mapping[date, ExceptionDay]


def weekly_by_day(intervals: Sequence[WeeklyInterval]) -> dict[int, list[tuple[int, int]]]:
    """Index a weekly interval list by day, each day sorted by opening."""
    by_day: dict[int, list[tuple[int, int]]] = {}
    for interval in intervals:
        by_day.setdefault(interval.day_of_week, []).append(
            (interval.opens_minute, interval.closes_minute)
        )
    for day_intervals in by_day.values():
        day_intervals.sort()
    return by_day


def intervals_for_local_date(
    day: date, weekly: Schedule, exceptions: Exceptions
) -> Sequence[tuple[int, int]]:
    """A date's authored intervals: the exception's, or the weekday's.

    Any exception fully replaces the weekly schedule for its date —
    including the empty (closed-all-day) exception. ``date.weekday()`` is
    already ISO Monday = 0, matching the stored encoding.
    """
    exception = exceptions.get(day)
    if exception is not None:
        return exception.intervals
    return weekly.get(day.weekday(), ())


def open_intervals(
    start_day: date,
    day_count: int,
    weekly: Schedule,
    exceptions: Exceptions,
    tz: ZoneInfo,
) -> Iterator[OpenInterval]:
    """Realized open intervals for ``day_count`` local dates, in instant order.

    Lazy by service day, so bounded consumers (next opening, first slot)
    do not convert a year of schedule up front. Yield order is globally
    sorted by ``opens_at``: openings are within their own local date, so
    day-major iteration with each day sorted is monotone.
    """
    for offset in range(day_count):
        day = start_day + timedelta(days=offset)
        for opens_minute, closes_minute in sorted(
            intervals_for_local_date(day, weekly, exceptions)
        ):
            opens_at = wall_to_instant(day, opens_minute, tz, boundary="open")
            closes_at = wall_to_instant(day, closes_minute, tz, boundary="close")
            if closes_at > opens_at:  # collapsed inside a gap: nothing exists
                yield OpenInterval(opens_at=opens_at, closes_at=closes_at)


def availability_at(
    now: datetime,
    *,
    weekly: Schedule,
    exceptions: Exceptions,
    policy: FulfillmentPolicy,
    tz: ZoneInfo,
) -> AvailabilityFacts:
    """The instant answers at ``now`` (an aware instant)."""
    now = now.astimezone(UTC)
    today = local_date(now, tz)
    # Start one service day back so an overnight interval that began the
    # previous local date is seen; scan forward bounded.
    start = today - timedelta(days=1)
    containing: list[OpenInterval] = []
    next_opens_at: datetime | None = None
    for interval in open_intervals(start, NEXT_OPENING_SCAN_DAYS + 1, weekly, exceptions, tz):
        if interval.opens_at <= now < interval.closes_at:
            containing.append(interval)
        elif interval.opens_at > now:
            next_opens_at = interval.opens_at
            break
    is_open = bool(containing)
    return AvailabilityFacts(
        is_open_now=is_open,
        # Two authored intervals may overlap across a day boundary (an
        # overnight spill under the next day's schedule); openness is
        # their union, so the honest close is the furthest one.
        closes_at=max(i.closes_at for i in containing) if is_open else None,
        next_opens_at=None if is_open else next_opens_at,
        next_pickup_at=(
            next_pickup_at(now, weekly=weekly, exceptions=exceptions, policy=policy, tz=tz)
            if policy.pickup_enabled
            else None
        ),
    )


def pickup_slots(
    now: datetime,
    *,
    weekly: Schedule,
    exceptions: Exceptions,
    policy: FulfillmentPolicy,
    tz: ZoneInfo,
    limit: int,
) -> list[datetime]:
    """Valid pickup instants from ``now``, at most ``limit`` of them.

    Slots step in **real time** (``slot_interval_minutes``) from each
    interval's opening instant, so spacing stays even across a DST
    transition inside an open interval (the local labels may jump — that
    is the transition, not an error). A slot is valid from
    ``now + lead_time`` through ``closes_at - last_order_before_close``.
    ``max_days_ahead`` bounds the **service day** (the local date whose
    schedule created the interval): day 0 is today, so 0 means same-day
    pickup only, and an overnight interval's small-hours slots belong to
    the service day that opened them.
    """
    if not policy.pickup_enabled or limit <= 0:
        return []
    now = now.astimezone(UTC)
    earliest = now + timedelta(minutes=policy.lead_time_minutes)
    step = timedelta(minutes=policy.slot_interval_minutes)
    today = local_date(now, tz)
    slots: list[datetime] = []
    # Service days: yesterday (an already-open overnight interval can still
    # take a pickup) through the scheduling horizon.
    for interval in open_intervals(
        today - timedelta(days=1),
        policy.max_days_ahead + 2,
        weekly,
        exceptions,
        tz,
    ):
        cutoff = interval.closes_at - timedelta(minutes=policy.last_order_before_close_minutes)
        slot = interval.opens_at
        if slot < earliest:
            behind = ceil((earliest - slot) / step)
            slot += behind * step
        while slot <= cutoff:
            slots.append(slot)
            if len(slots) >= limit:
                return slots
            slot += step
    return slots


def next_pickup_at(
    now: datetime,
    *,
    weekly: Schedule,
    exceptions: Exceptions,
    policy: FulfillmentPolicy,
    tz: ZoneInfo,
) -> datetime | None:
    """The earliest valid pickup instant, or None when none exists."""
    slots = pickup_slots(now, weekly=weekly, exceptions=exceptions, policy=policy, tz=tz, limit=1)
    return slots[0] if slots else None


def find_weekly_overlap(
    intervals: Sequence[WeeklyInterval],
) -> tuple[WeeklyInterval, WeeklyInterval] | None:
    """The first overlapping pair in a submitted weekly set, or None.

    Overlap is computed on the 10,080-minute week circle, so a Sunday
    interval running past midnight is checked against Monday's openings.
    Purely arithmetic — validating the full submitted set is what makes
    the full-week replacement command self-contained (ADR-025).
    """
    week = 7 * 1440
    segments: list[tuple[int, int, WeeklyInterval]] = []
    for interval in intervals:
        start = interval.day_of_week * 1440 + interval.opens_minute
        end = interval.day_of_week * 1440 + interval.closes_minute
        if end <= week:
            segments.append((start, end, interval))
        else:  # wraps past the end of the week circle
            segments.append((start, week, interval))
            segments.append((0, end - week, interval))
    segments.sort(key=lambda s: (s[0], s[1]))
    # Sorted by start, any overlap implies an overlapping *adjacent* pair,
    # so one pass suffices. A wrapped interval's own two segments are the
    # only permitted adjacency (duration <= 1440 makes self-overlap
    # impossible on a 10,080 circle).
    for (_, end_a, a), (start_b, _, b) in pairwise(segments):
        if a is not b and start_b < end_a:
            return (a, b)
    return None


def find_day_overlap(
    intervals: Sequence[tuple[int, int]],
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """The first overlapping pair within one date's submitted set, or None.

    Exception intervals live on one date's minute line (an overnight close
    simply extends it); cross-date spill against a neighbouring date's
    schedule is deliberately permitted and harmless — openness is a union.
    """
    ordered = sorted(intervals)
    for (opens_a, closes_a), following in pairwise(ordered):
        if following[0] < closes_a:
            return ((opens_a, closes_a), following)
    return None
