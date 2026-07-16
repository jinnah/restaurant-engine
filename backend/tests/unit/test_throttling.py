"""Login backoff schedule (M2A, ADR-010): pure-function behavior."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domains.identity.throttling import (
    BACKOFF_CAP_SECONDS,
    BACKOFF_THRESHOLD,
    is_throttled,
    required_backoff_seconds,
)


class TestRequiredBackoffSeconds:
    @pytest.mark.parametrize("count", range(BACKOFF_THRESHOLD))
    def test_no_backoff_under_the_threshold(self, count: int) -> None:
        assert required_backoff_seconds(count) == 0

    def test_doubling_schedule_from_the_threshold(self) -> None:
        # 5 failures -> 1s, then 2, 4, 8, 16, 32, then capped.
        schedule = [required_backoff_seconds(BACKOFF_THRESHOLD + i) for i in range(8)]
        assert schedule == [1, 2, 4, 8, 16, 32, 60, 60]

    def test_extreme_counts_stay_capped_without_overflow(self) -> None:
        assert required_backoff_seconds(10_000) == BACKOFF_CAP_SECONDS


class TestIsThrottled:
    NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)

    def test_never_throttled_under_the_threshold(self) -> None:
        assert not is_throttled(BACKOFF_THRESHOLD - 1, self.NOW, now=self.NOW)

    def test_throttled_inside_the_window(self) -> None:
        last_failed = self.NOW - timedelta(seconds=0.5)
        assert is_throttled(BACKOFF_THRESHOLD, last_failed, now=self.NOW)

    def test_free_after_the_window_elapses(self) -> None:
        last_failed = self.NOW - timedelta(seconds=1)
        assert not is_throttled(BACKOFF_THRESHOLD, last_failed, now=self.NOW)

    def test_missing_timestamp_means_not_throttled(self) -> None:
        # DB pairing CK makes count>0 with NULL timestamp impossible; the
        # function still degrades safely.
        assert not is_throttled(BACKOFF_THRESHOLD + 3, None, now=self.NOW)

    def test_cap_bounds_the_worst_case_wait(self) -> None:
        last_failed = self.NOW - timedelta(seconds=BACKOFF_CAP_SECONDS)
        assert not is_throttled(10_000, last_failed, now=self.NOW)
