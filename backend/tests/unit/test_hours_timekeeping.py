"""The DST contract, proven exhaustively (M5A, ADR-025).

These are the tests the Milestone 5 exit criteria name: gap behavior,
fall-back ambiguity, overnight intervals across transitions, and the
calendar rules — all pure functions of an injected clock, so every case is
deterministic and none depends on when the suite runs.

Zone choices are deliberate: America/New_York (the launch default, both
transitions), America/Phoenix (no DST at all), Australia/Sydney (southern
hemisphere — DST across the year boundary, transitions on the opposite
calendar side), and Australia/Lord_Howe (a 30-minute shift, the smallest
real-world transition, which breaks any hour-granularity assumption).
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domains.hours.timekeeping import local_date, wall_to_instant

NEW_YORK = ZoneInfo("America/New_York")
PHOENIX = ZoneInfo("America/Phoenix")
SYDNEY = ZoneInfo("Australia/Sydney")
LORD_HOWE = ZoneInfo("Australia/Lord_Howe")

# 2026 transitions, America/New_York: spring forward Sunday 2026-03-08
# (02:00 EST -> 03:00 EDT), fall back Sunday 2026-11-01 (02:00 EDT ->
# 01:00 EST).
SPRING_FORWARD = date(2026, 3, 8)
FALL_BACK = date(2026, 11, 1)


def utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestOrdinaryConversion:
    def test_plain_afternoon_is_offset_exact(self) -> None:
        # 14:00 EST on a plain winter day is 19:00Z.
        instant = wall_to_instant(date(2026, 1, 15), 14 * 60, NEW_YORK, boundary="open")
        assert instant == utc(2026, 1, 15, 19)

    def test_summer_offset_differs_from_winter(self) -> None:
        # The same wall time in July is EDT: 18:00Z.
        instant = wall_to_instant(date(2026, 7, 15), 14 * 60, NEW_YORK, boundary="open")
        assert instant == utc(2026, 7, 15, 18)

    def test_open_and_close_agree_for_unambiguous_times(self) -> None:
        for minute in (0, 9 * 60 + 30, 23 * 60 + 59):
            assert wall_to_instant(
                date(2026, 5, 4), minute, NEW_YORK, boundary="open"
            ) == wall_to_instant(date(2026, 5, 4), minute, NEW_YORK, boundary="close")

    def test_result_is_utc(self) -> None:
        instant = wall_to_instant(date(2026, 5, 4), 600, NEW_YORK, boundary="open")
        assert instant.tzinfo == UTC


class TestOvernightMinutes:
    def test_minutes_past_1439_roll_into_the_next_local_day(self) -> None:
        # Friday 26:00 (= Saturday 02:00) in January: 07:00Z Saturday.
        instant = wall_to_instant(date(2026, 1, 16), 26 * 60, NEW_YORK, boundary="close")
        assert instant == utc(2026, 1, 17, 7)

    def test_1440_is_midnight_at_the_end_of_the_day(self) -> None:
        instant = wall_to_instant(date(2026, 1, 16), 1440, NEW_YORK, boundary="close")
        assert instant == utc(2026, 1, 17, 5)


class TestSpringForwardGap:
    """02:00-03:00 local does not exist on 2026-03-08 in New York."""

    def test_a_time_inside_the_gap_moves_to_the_gap_end(self) -> None:
        # 02:30 does not exist; the rule moves it to 03:00 EDT = 07:00Z.
        for boundary in ("open", "close"):
            instant = wall_to_instant(SPRING_FORWARD, 2 * 60 + 30, NEW_YORK, boundary=boundary)
            assert instant == utc(2026, 3, 8, 7)
            # And the resolved local wall time is exactly the gap's end.
            assert instant.astimezone(NEW_YORK).strftime("%H:%M") == "03:00"

    def test_the_gap_start_itself_moves_to_the_gap_end(self) -> None:
        # 02:00 is the first nonexistent minute.
        instant = wall_to_instant(SPRING_FORWARD, 2 * 60, NEW_YORK, boundary="open")
        assert instant == utc(2026, 3, 8, 7)

    def test_the_minute_before_the_gap_is_unmoved(self) -> None:
        # 01:59 EST exists: 06:59Z.
        instant = wall_to_instant(SPRING_FORWARD, 1 * 60 + 59, NEW_YORK, boundary="open")
        assert instant == utc(2026, 3, 8, 6, 59)

    def test_the_gap_end_itself_is_unmoved(self) -> None:
        # 03:00 EDT exists: 07:00Z.
        instant = wall_to_instant(SPRING_FORWARD, 3 * 60, NEW_YORK, boundary="open")
        assert instant == utc(2026, 3, 8, 7)

    def test_every_minute_of_the_gap_resolves_to_the_gap_end(self) -> None:
        # Exhaustive over the whole nonexistent hour, both boundaries.
        for minute in range(2 * 60, 3 * 60):
            for boundary in ("open", "close"):
                assert wall_to_instant(SPRING_FORWARD, minute, NEW_YORK, boundary=boundary) == utc(
                    2026, 3, 8, 7
                ), f"minute {minute} ({boundary})"

    def test_an_overnight_close_landing_in_the_gap_moves_forward(self) -> None:
        # Saturday 26:30 = Sunday 02:30, which does not exist on the
        # spring-forward Sunday: the close moves to 03:00 EDT.
        instant = wall_to_instant(
            SPRING_FORWARD.replace(day=7), 26 * 60 + 30, NEW_YORK, boundary="close"
        )
        assert instant == utc(2026, 3, 8, 7)


class TestFallBackAmbiguity:
    """01:00-02:00 local occurs twice on 2026-11-01 in New York."""

    def test_open_takes_the_earlier_occurrence(self) -> None:
        # First 01:30 is EDT: 05:30Z.
        instant = wall_to_instant(FALL_BACK, 1 * 60 + 30, NEW_YORK, boundary="open")
        assert instant == utc(2026, 11, 1, 5, 30)

    def test_close_takes_the_later_occurrence(self) -> None:
        # Second 01:30 is EST: 06:30Z — the union rule: a business
        # advertising 01:00-02:00 is open the whole repeated hour.
        instant = wall_to_instant(FALL_BACK, 1 * 60 + 30, NEW_YORK, boundary="close")
        assert instant == utc(2026, 11, 1, 6, 30)

    def test_the_ambiguous_window_is_one_hour_apart_by_boundary(self) -> None:
        for minute in range(1 * 60, 2 * 60):
            opened = wall_to_instant(FALL_BACK, minute, NEW_YORK, boundary="open")
            closed = wall_to_instant(FALL_BACK, minute, NEW_YORK, boundary="close")
            assert (closed - opened).total_seconds() == 3600, f"minute {minute}"

    def test_a_time_after_the_repeated_hour_is_unambiguous(self) -> None:
        # 02:30 EST exists once: 07:30Z.
        for boundary in ("open", "close"):
            assert wall_to_instant(FALL_BACK, 2 * 60 + 30, NEW_YORK, boundary=boundary) == utc(
                2026, 11, 1, 7, 30
            )

    def test_an_overnight_interval_spanning_fall_back_is_real_length(self) -> None:
        # Saturday 20:00 EDT -> Sunday 02:00 EST is 20:00-02:00 on the wall
        # but seven real hours: end-to-end conversion, never duration.
        opens = wall_to_instant(date(2026, 10, 31), 20 * 60, NEW_YORK, boundary="open")
        closes = wall_to_instant(date(2026, 10, 31), 26 * 60, NEW_YORK, boundary="close")
        assert (closes - opens).total_seconds() == 7 * 3600

    def test_an_overnight_interval_spanning_spring_forward_is_real_length(self) -> None:
        # Saturday 20:00 EST -> Sunday 04:00 EDT reads eight wall hours but
        # is seven real ones.
        opens = wall_to_instant(date(2026, 3, 7), 20 * 60, NEW_YORK, boundary="open")
        closes = wall_to_instant(date(2026, 3, 7), 28 * 60, NEW_YORK, boundary="close")
        assert (closes - opens).total_seconds() == 7 * 3600


class TestZonesWithoutSurprises:
    def test_phoenix_has_no_transitions(self) -> None:
        # Arizona observes no DST: both boundary kinds agree at every
        # spring-forward-adjacent minute, offset is always -7.
        for minute in range(0, 1440, 30):
            opened = wall_to_instant(SPRING_FORWARD, minute, PHOENIX, boundary="open")
            closed = wall_to_instant(SPRING_FORWARD, minute, PHOENIX, boundary="close")
            assert opened == closed
        assert wall_to_instant(SPRING_FORWARD, 720, PHOENIX, boundary="open") == utc(2026, 3, 8, 19)

    def test_utc_is_the_identity_bridge(self) -> None:
        instant = wall_to_instant(date(2026, 6, 1), 8 * 60, ZoneInfo("UTC"), boundary="open")
        assert instant == utc(2026, 6, 1, 8)


class TestSouthernHemisphere:
    """Sydney: DST *starts* in October and *ends* in April."""

    def test_sydney_spring_forward_gap_in_october(self) -> None:
        # 2026-10-04: 02:00 AEST -> 03:00 AEDT; 02:30 does not exist and
        # moves to 03:00 AEDT = 16:00Z on the previous UTC day.
        instant = wall_to_instant(date(2026, 10, 4), 2 * 60 + 30, SYDNEY, boundary="open")
        assert instant == utc(2026, 10, 3, 16)
        assert instant.astimezone(SYDNEY).strftime("%H:%M") == "03:00"

    def test_sydney_fall_back_ambiguity_in_april(self) -> None:
        # 2026-04-05: 03:00 AEDT -> 02:00 AEST; 02:30 occurs twice.
        opened = wall_to_instant(date(2026, 4, 5), 2 * 60 + 30, SYDNEY, boundary="open")
        closed = wall_to_instant(date(2026, 4, 5), 2 * 60 + 30, SYDNEY, boundary="close")
        assert (closed - opened).total_seconds() == 3600
        assert opened == utc(2026, 4, 4, 15, 30)  # AEDT (+11)
        assert closed == utc(2026, 4, 4, 16, 30)  # AEST (+10)


class TestSubHourTransition:
    """Lord Howe Island shifts by thirty minutes, not an hour."""

    def test_the_gap_is_thirty_minutes_wide(self) -> None:
        # 2026-10-04: 02:00 +10:30 -> 02:30 +11:00; 02:15 does not exist
        # and moves to the gap end 02:30 (+11) = 15:30Z previous UTC day.
        instant = wall_to_instant(date(2026, 10, 4), 2 * 60 + 15, LORD_HOWE, boundary="open")
        assert instant.astimezone(LORD_HOWE).strftime("%H:%M") == "02:30"
        assert instant == utc(2026, 10, 3, 15, 30)

    def test_the_ambiguity_is_thirty_minutes_apart(self) -> None:
        # 2026-04-05: 02:00 +11:00 -> 01:30 +10:30; 01:45 occurs twice,
        # thirty real minutes apart.
        opened = wall_to_instant(date(2026, 4, 5), 1 * 60 + 45, LORD_HOWE, boundary="open")
        closed = wall_to_instant(date(2026, 4, 5), 1 * 60 + 45, LORD_HOWE, boundary="close")
        assert (closed - opened).total_seconds() == 30 * 60


class TestLocalDate:
    def test_the_tenant_calendar_not_utc(self) -> None:
        # 03:30Z on June 2 is still June 1 in New York (23:30 EDT).
        now = utc(2026, 6, 2, 3, 30)
        assert local_date(now, NEW_YORK) == date(2026, 6, 1)
        # …and already June 2 in Sydney (13:30 AEST).
        assert local_date(now, SYDNEY) == date(2026, 6, 2)

    def test_a_non_utc_aware_instant_is_normalized_first(self) -> None:
        # The same instant expressed in another zone gives the same answer.
        now = utc(2026, 6, 2, 3, 30).astimezone(SYDNEY)
        assert local_date(now, NEW_YORK) == date(2026, 6, 1)
