"""Availability, precedence, and pickup-slot rules (M5A, ADR-025).

Every case injects its own ``now``: nothing here depends on the wall clock,
which is precisely why the closure / lead-time / next-opening exit criteria
can be met at this layer.
"""

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import ClassVar
from zoneinfo import ZoneInfo

from app.domains.hours.availability import (
    AvailabilityFacts,
    ExceptionDay,
    FulfillmentPolicy,
    WeeklyInterval,
    availability_at,
    find_day_overlap,
    find_weekly_overlap,
    intervals_for_local_date,
    next_pickup_at,
    pickup_slots,
    weekly_by_day,
)

NEW_YORK = ZoneInfo("America/New_York")

DISABLED = FulfillmentPolicy(
    pickup_enabled=False,
    asap_enabled=True,
    lead_time_minutes=20,
    slot_interval_minutes=15,
    last_order_before_close_minutes=30,
    max_days_ahead=0,
)
PICKUP = FulfillmentPolicy(
    pickup_enabled=True,
    asap_enabled=True,
    lead_time_minutes=20,
    slot_interval_minutes=15,
    last_order_before_close_minutes=30,
    max_days_ahead=0,
)


def utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def facts(
    now: datetime,
    weekly: dict[int, list[tuple[int, int]]],
    exceptions: dict[date, ExceptionDay] | None = None,
    policy: FulfillmentPolicy = DISABLED,
) -> AvailabilityFacts:
    return availability_at(
        now, weekly=weekly, exceptions=exceptions or {}, policy=policy, tz=NEW_YORK
    )


# Monday-Friday 11:00-21:00 (2026-01-05 is a Monday).
WEEKDAYS_11_TO_21 = {dow: [(11 * 60, 21 * 60)] for dow in range(5)}


class TestOpenNow:
    def test_open_inside_an_interval(self) -> None:
        # Monday 12:00 EST = 17:00Z.
        result = facts(utc(2026, 1, 5, 17), WEEKDAYS_11_TO_21)
        assert result.is_open_now is True
        assert result.closes_at == utc(2026, 1, 6, 2)  # 21:00 EST
        assert result.next_opens_at is None

    def test_openness_is_instant_containment_at_the_edges(self) -> None:
        opens = utc(2026, 1, 5, 16)  # 11:00 EST
        closes = utc(2026, 1, 6, 2)  # 21:00 EST
        assert facts(opens, WEEKDAYS_11_TO_21).is_open_now is True  # inclusive open
        assert facts(closes, WEEKDAYS_11_TO_21).is_open_now is False  # exclusive close
        assert facts(closes - timedelta(minutes=1), WEEKDAYS_11_TO_21).is_open_now is True

    def test_closed_before_opening_reports_todays_opening(self) -> None:
        result = facts(utc(2026, 1, 5, 14), WEEKDAYS_11_TO_21)  # Monday 09:00 EST
        assert result.is_open_now is False
        assert result.next_opens_at == utc(2026, 1, 5, 16)
        assert result.closes_at is None

    def test_closed_across_the_weekend_finds_monday(self) -> None:
        # Friday 22:00 EST (2026-01-09) -> next opening Monday 11:00 EST.
        result = facts(utc(2026, 1, 10, 3), WEEKDAYS_11_TO_21)
        assert result.is_open_now is False
        assert result.next_opens_at == utc(2026, 1, 12, 16)

    def test_no_hours_at_all_terminates_with_none(self) -> None:
        result = facts(utc(2026, 1, 5, 17), {})
        assert result == AvailabilityFacts(
            is_open_now=False, closes_at=None, next_opens_at=None, next_pickup_at=None
        )

    def test_split_service_reports_the_current_sitting(self) -> None:
        weekly = {0: [(11 * 60, 14 * 60), (17 * 60, 21 * 60)]}
        gap = facts(utc(2026, 1, 5, 20), weekly)  # Monday 15:00 EST
        assert gap.is_open_now is False
        assert gap.next_opens_at == utc(2026, 1, 5, 22)  # 17:00 EST
        lunch = facts(utc(2026, 1, 5, 18), weekly)  # 13:00 EST
        assert lunch.is_open_now is True
        assert lunch.closes_at == utc(2026, 1, 5, 19)  # 14:00 EST


class TestOvernight:
    # Friday 17:00-02:00 (Saturday morning). ClassVar: shared fixture
    # data, never mutated.
    FRIDAY_NIGHT: ClassVar[dict[int, list[tuple[int, int]]]] = {4: [(17 * 60, 26 * 60)]}

    def test_the_small_hours_belong_to_the_service_day(self) -> None:
        # Saturday 01:30 EST = 06:30Z: still Friday's service.
        result = facts(utc(2026, 1, 10, 6, 30), self.FRIDAY_NIGHT)
        assert result.is_open_now is True
        assert result.closes_at == utc(2026, 1, 10, 7)

    def test_closed_after_the_overnight_service_ends(self) -> None:
        result = facts(utc(2026, 1, 10, 7, 30), self.FRIDAY_NIGHT)
        assert result.is_open_now is False
        # Next Friday.
        assert result.next_opens_at == utc(2026, 1, 16, 22)

    def test_an_overnight_interval_survives_the_next_days_closure(self) -> None:
        # Saturday is closed by exception; Friday night still runs to 2 a.m.
        # Saturday, because it is Friday's service (ADR-025).
        exceptions = {
            date(2026, 1, 10): ExceptionDay(
                exception_date=date(2026, 1, 10), intervals=(), note=None
            )
        }
        result = facts(utc(2026, 1, 10, 6, 30), self.FRIDAY_NIGHT, exceptions)
        assert result.is_open_now is True

    def test_a_closure_on_the_service_day_kills_the_whole_interval(self) -> None:
        exceptions = {
            date(2026, 1, 9): ExceptionDay(exception_date=date(2026, 1, 9), intervals=(), note=None)
        }
        result = facts(utc(2026, 1, 10, 6, 30), self.FRIDAY_NIGHT, exceptions)
        assert result.is_open_now is False


class TestExceptionPrecedence:
    def test_a_closure_overrides_an_open_weekday(self) -> None:
        exceptions = {
            date(2026, 1, 5): ExceptionDay(
                exception_date=date(2026, 1, 5), intervals=(), note="Closed for Eid"
            )
        }
        result = facts(utc(2026, 1, 5, 17), WEEKDAYS_11_TO_21, exceptions)
        assert result.is_open_now is False
        assert result.next_opens_at == utc(2026, 1, 6, 16)  # Tuesday 11:00

    def test_special_hours_override_a_closed_weekday(self) -> None:
        # Saturday has no weekly hours; an exception opens 10:00-15:00.
        exceptions = {
            date(2026, 1, 10): ExceptionDay(
                exception_date=date(2026, 1, 10),
                intervals=((10 * 60, 15 * 60),),
                note=None,
            )
        }
        result = facts(utc(2026, 1, 10, 16), WEEKDAYS_11_TO_21, exceptions)
        assert result.is_open_now is True
        assert result.closes_at == utc(2026, 1, 10, 20)

    def test_the_exception_replaces_rather_than_merges(self) -> None:
        # Monday's exception 09:00-10:00: the weekly 11:00-21:00 is gone.
        exceptions = {
            date(2026, 1, 5): ExceptionDay(
                exception_date=date(2026, 1, 5),
                intervals=((9 * 60, 10 * 60),),
                note=None,
            )
        }
        result = facts(utc(2026, 1, 5, 17), WEEKDAYS_11_TO_21, exceptions)  # 12:00 EST
        assert result.is_open_now is False

    def test_the_exception_calendar_is_tenant_local(self) -> None:
        # 03:00Z Tuesday is still Monday 22:00 EST: Monday's closure must
        # not bleed into what is already Tuesday in UTC. Weekly hours run
        # to 23:00 for this case so the boundary is observable.
        weekly = {dow: [(11 * 60, 23 * 60)] for dow in range(5)}
        exceptions = {
            date(2026, 1, 5): ExceptionDay(exception_date=date(2026, 1, 5), intervals=(), note=None)
        }
        monday_night = facts(utc(2026, 1, 6, 3), weekly, exceptions)
        assert monday_night.is_open_now is False  # Monday is the closed date
        tuesday_night = facts(utc(2026, 1, 7, 3), weekly, exceptions)
        assert tuesday_night.is_open_now is True  # Tuesday is untouched


class TestDstDays:
    def test_spring_forward_shortens_an_early_interval(self) -> None:
        # Sunday 01:00-03:00 on the spring-forward date: 02:00-03:00 does
        # not exist, so the realized interval is 01:00-03:00(EDT) = one
        # real hour, and 02:30 wall never happens.
        weekly = {6: [(1 * 60, 3 * 60)]}
        opens_check = facts(utc(2026, 3, 8, 6, 30), weekly)  # 01:30 EST
        assert opens_check.is_open_now is True
        assert opens_check.closes_at == utc(2026, 3, 8, 7)  # 03:00 EDT

    def test_an_interval_entirely_inside_the_gap_never_exists(self) -> None:
        weekly = {6: [(2 * 60, 3 * 60)]}  # 02:00-03:00 on the gap Sunday
        result = facts(utc(2026, 3, 8, 6, 30), weekly)
        assert result.is_open_now is False
        # The next occurrence (2026-03-15) exists normally: 02:00 EDT.
        assert result.next_opens_at == utc(2026, 3, 15, 6)

    def test_fall_back_lengthens_the_repeated_window(self) -> None:
        # Sunday 01:00-02:00 on the fall-back date: open takes the first
        # 01:00 (EDT), close the second 02:00 (EST) — two real hours.
        weekly = {6: [(1 * 60, 2 * 60)]}
        result = facts(utc(2026, 11, 1, 6, 30), weekly)  # inside the repeat
        assert result.is_open_now is True
        assert result.closes_at == utc(2026, 11, 1, 7)  # 02:00 EST


class TestNextOpeningBounds:
    def test_across_a_multi_day_closure(self) -> None:
        exceptions = {
            date(2026, 1, 5) + timedelta(days=n): ExceptionDay(
                exception_date=date(2026, 1, 5) + timedelta(days=n),
                intervals=(),
                note=None,
            )
            for n in range(10)
        }
        result = facts(utc(2026, 1, 5, 17), WEEKDAYS_11_TO_21, exceptions)
        # First weekly day after the closure block: Thursday 2026-01-15.
        assert result.next_opens_at == utc(2026, 1, 15, 16)

    def test_across_the_year_boundary(self) -> None:
        # Weekly hours only on Friday; from Saturday 2026-12-26 the next
        # Friday is 2027-01-01.
        weekly = {4: [(11 * 60, 21 * 60)]}
        result = facts(utc(2026, 12, 26, 17), weekly)
        assert result.next_opens_at == utc(2027, 1, 1, 16)


class TestPickupSlots:
    def test_disabled_pickup_yields_nothing(self) -> None:
        result = facts(utc(2026, 1, 5, 17), WEEKDAYS_11_TO_21, policy=DISABLED)
        assert result.next_pickup_at is None
        assert (
            pickup_slots(
                utc(2026, 1, 5, 17),
                weekly=WEEKDAYS_11_TO_21,
                exceptions={},
                policy=DISABLED,
                tz=NEW_YORK,
                limit=5,
            )
            == []
        )

    def test_lead_time_pushes_the_first_slot(self) -> None:
        # Monday 12:00 EST, lead 20, slots every 15 from the 11:00 opening:
        # the first slot >= 12:20 on the :00/:15/:30/:45 grid is 12:30.
        first = next_pickup_at(
            utc(2026, 1, 5, 17),
            weekly=WEEKDAYS_11_TO_21,
            exceptions={},
            policy=PICKUP,
            tz=NEW_YORK,
        )
        assert first == utc(2026, 1, 5, 17, 30)

    def test_before_opening_the_first_slot_is_the_opening(self) -> None:
        # Monday 09:00 EST: lead time lands before opening, so the first
        # slot is the opening itself.
        first = next_pickup_at(
            utc(2026, 1, 5, 14),
            weekly=WEEKDAYS_11_TO_21,
            exceptions={},
            policy=PICKUP,
            tz=NEW_YORK,
        )
        assert first == utc(2026, 1, 5, 16)

    def test_the_cutoff_blocks_the_end_of_service(self) -> None:
        # Monday 20:45 EST, close 21:00, cutoff 30 minutes: nothing left
        # today, and max_days_ahead=0 forbids tomorrow.
        first = next_pickup_at(
            utc(2026, 1, 6, 1, 45),
            weekly=WEEKDAYS_11_TO_21,
            exceptions={},
            policy=PICKUP,
            tz=NEW_YORK,
        )
        assert first is None

    def test_lead_time_at_the_cutoff_boundary_is_exact(self) -> None:
        # Monday 20:10 EST + 20 lead = 20:30 exactly, which is exactly the
        # cutoff (21:00 - 30): the slot at 20:30 is valid, nothing later.
        slots = pickup_slots(
            utc(2026, 1, 6, 1, 10),
            weekly=WEEKDAYS_11_TO_21,
            exceptions={},
            policy=PICKUP,
            tz=NEW_YORK,
            limit=10,
        )
        assert slots == [utc(2026, 1, 6, 1, 30)]

    def test_max_days_ahead_admits_the_next_service_day(self) -> None:
        late = utc(2026, 1, 6, 1, 45)  # Monday 20:45 EST, today exhausted
        policy = FulfillmentPolicy(
            pickup_enabled=True,
            asap_enabled=True,
            lead_time_minutes=20,
            slot_interval_minutes=15,
            last_order_before_close_minutes=30,
            max_days_ahead=1,
        )
        first = next_pickup_at(
            late, weekly=WEEKDAYS_11_TO_21, exceptions={}, policy=policy, tz=NEW_YORK
        )
        assert first == utc(2026, 1, 6, 16)  # Tuesday 11:00 opening

    def test_slots_step_evenly_across_a_transition(self) -> None:
        # Fall-back night, Saturday 20:00-26:00 service (2026-10-31):
        # slots remain 15 real minutes apart across the repeated hour.
        weekly = {5: [(20 * 60, 26 * 60)]}
        policy = FulfillmentPolicy(
            pickup_enabled=True,
            asap_enabled=True,
            lead_time_minutes=0,
            slot_interval_minutes=15,
            last_order_before_close_minutes=0,
            max_days_ahead=0,
        )
        slots = pickup_slots(
            utc(2026, 11, 1, 4, 0),  # 00:00 EDT Sunday, inside the service
            weekly=weekly,
            exceptions={},
            policy=policy,
            tz=NEW_YORK,
            limit=200,
        )
        assert len(slots) >= 2
        deltas = {(b - a).total_seconds() for a, b in pairwise(slots)}
        assert deltas == {15 * 60}
        # The service really ends at 02:00 EST = 07:00Z; the last slot is
        # at the close (cutoff 0).
        assert slots[-1] == utc(2026, 11, 1, 7)

    def test_slots_belong_to_the_service_day(self) -> None:
        # Saturday overnight service; Sunday 00:30 EST: the small-hours
        # slots come from Saturday (day -1 relative to local today).
        weekly = {5: [(20 * 60, 26 * 60)]}
        policy = FulfillmentPolicy(
            pickup_enabled=True,
            asap_enabled=True,
            lead_time_minutes=0,
            slot_interval_minutes=30,
            last_order_before_close_minutes=0,
            max_days_ahead=0,
        )
        slots = pickup_slots(
            utc(2026, 1, 11, 5, 40),  # Sunday 00:40 EST
            weekly=weekly,
            exceptions={},
            policy=policy,
            tz=NEW_YORK,
            limit=10,
        )
        # Remaining Saturday-service slots: 01:00, 01:30, 02:00 EST.
        assert slots == [utc(2026, 1, 11, 6), utc(2026, 1, 11, 6, 30), utc(2026, 1, 11, 7)]

    def test_limit_bounds_the_enumeration(self) -> None:
        slots = pickup_slots(
            utc(2026, 1, 5, 17),
            weekly=WEEKDAYS_11_TO_21,
            exceptions={},
            policy=PICKUP,
            tz=NEW_YORK,
            limit=3,
        )
        assert len(slots) == 3


class TestOverlapValidation:
    def test_disjoint_weekly_intervals_pass(self) -> None:
        intervals = [
            WeeklyInterval(0, 11 * 60, 14 * 60),
            WeeklyInterval(0, 17 * 60, 21 * 60),
            WeeklyInterval(1, 11 * 60, 21 * 60),
        ]
        assert find_weekly_overlap(intervals) is None

    def test_same_day_overlap_is_found(self) -> None:
        intervals = [
            WeeklyInterval(0, 11 * 60, 15 * 60),
            WeeklyInterval(0, 14 * 60, 21 * 60),
        ]
        assert find_weekly_overlap(intervals) is not None

    def test_touching_intervals_do_not_overlap(self) -> None:
        intervals = [
            WeeklyInterval(0, 11 * 60, 14 * 60),
            WeeklyInterval(0, 14 * 60, 21 * 60),
        ]
        assert find_weekly_overlap(intervals) is None

    def test_an_overnight_interval_collides_with_the_next_morning(self) -> None:
        intervals = [
            WeeklyInterval(0, 20 * 60, 26 * 60),  # Monday 20:00-02:00 Tue
            WeeklyInterval(1, 1 * 60, 9 * 60),  # Tuesday 01:00-09:00
        ]
        assert find_weekly_overlap(intervals) is not None

    def test_sunday_overnight_wraps_onto_monday(self) -> None:
        intervals = [
            WeeklyInterval(6, 20 * 60, 26 * 60),  # Sunday 20:00-02:00 Mon
            WeeklyInterval(0, 1 * 60, 9 * 60),  # Monday 01:00-09:00
        ]
        assert find_weekly_overlap(intervals) is not None

    def test_sunday_overnight_clear_of_monday_passes(self) -> None:
        intervals = [
            WeeklyInterval(6, 20 * 60, 26 * 60),
            WeeklyInterval(0, 2 * 60, 9 * 60),  # starts exactly at the wrap end
        ]
        assert find_weekly_overlap(intervals) is None

    def test_day_overlap_within_one_exception_date(self) -> None:
        assert find_day_overlap([(600, 720), (700, 800)]) is not None
        assert find_day_overlap([(600, 720), (720, 800)]) is None


class TestHelpers:
    def test_weekly_by_day_sorts_each_day(self) -> None:
        by_day = weekly_by_day(
            [WeeklyInterval(0, 17 * 60, 21 * 60), WeeklyInterval(0, 11 * 60, 14 * 60)]
        )
        assert by_day == {0: [(660, 840), (1020, 1260)]}

    def test_intervals_for_local_date_prefers_the_exception(self) -> None:
        weekly = {0: [(660, 1260)]}
        exceptions = {
            date(2026, 1, 5): ExceptionDay(
                exception_date=date(2026, 1, 5), intervals=((600, 900),), note=None
            )
        }
        assert intervals_for_local_date(date(2026, 1, 5), weekly, exceptions) == ((600, 900),)
        assert intervals_for_local_date(date(2026, 1, 12), weekly, exceptions) == [(660, 1260)]
