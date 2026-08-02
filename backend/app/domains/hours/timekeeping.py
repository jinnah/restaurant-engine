"""Wall-clock to instant conversion under the tenant timezone (M5A, ADR-025).

Pure functions with no database and no ambient clock — ``now`` is always an
argument where one is needed. This is the module the DST exit criteria are
met in, so its rules are stated once, here, and tested exhaustively:

* **Storage is local wall time**; the tenant's IANA zone is the only
  bridge, resolved through ``zoneinfo`` at computation time.
* **Spring-forward gaps** (a local time that does not exist):
  ``zoneinfo`` does not raise — it silently shifts. Nonexistence is
  detected explicitly and the boundary moves **forward to the end of the
  gap**, the transition instant itself. A 02:30 opening on the
  spring-forward date opens at 03:00 local.
* **Fall-back ambiguity** (a local time that occurs twice): opening
  boundaries take the earlier occurrence (``fold=0``), closing boundaries
  the later (``fold=1``), so the open window is the union. The closing
  rule must be written — ``fold=0`` is Python's default, and omission
  would silently halve the repeated hour.
* **Overnight minutes**: a minute value above 1439 rolls into the
  following local day before conversion (ruling D1), so each boundary is
  converted independently, end-to-end — never start-plus-duration.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.domains.hours.policies import MINUTES_PER_DAY

Boundary = Literal["open", "close"]


def wall_to_instant(day: date, minute: int, tz: ZoneInfo, *, boundary: Boundary) -> datetime:
    """The UTC instant of ``minute`` minutes after ``day``'s local midnight.

    ``minute`` may exceed 1439 (an overnight close, D1) and rolls into the
    following day. The gap and ambiguity rules above decide the instant
    when the wall time does not exist or exists twice.
    """
    day += timedelta(days=minute // MINUTES_PER_DAY)
    minute %= MINUTES_PER_DAY
    naive = datetime.combine(day, time(hour=minute // 60, minute=minute % 60))
    # The two fold conversions agree exactly when the wall time exists
    # unambiguously. For a nonexistent (gap) time, fold=0 applies the
    # pre-transition offset and lands *after* fold=1 — the reversed order
    # is the gap signature. For an ambiguous (repeated) time, fold=0 is
    # the earlier real occurrence.
    first = naive.replace(tzinfo=tz, fold=0).astimezone(UTC)
    second = naive.replace(tzinfo=tz, fold=1).astimezone(UTC)
    if first == second:
        return first
    if first > second:
        return _transition_instant(second, first, tz)
    return first if boundary == "open" else second


def local_date(now: datetime, tz: ZoneInfo) -> date:
    """The tenant's local calendar date at ``now`` (an aware instant).

    Never the server's date and never UTC's date: at 23:30 local a
    business is on a different UTC date for hours a day, and using the
    wrong calendar makes every exception lookup off by one.
    """
    return now.astimezone(tz).date()


def _transition_instant(low: datetime, high: datetime, tz: ZoneInfo) -> datetime:
    """The first instant in ``[low, high]`` carrying ``high``'s UTC offset.

    ``low`` and ``high`` are the two fold conversions of a nonexistent
    local time, so they bracket exactly one transition; its instant is the
    end of the gap — the moment the clock jumps to the gap's far side.
    Bisected to the minute (every real-world transition is minute-aligned).
    """
    target = high.astimezone(tz).utcoffset()
    lo, hi = 0, int((high - low).total_seconds() // 60)
    while lo < hi:
        mid = (lo + hi) // 2
        if (low + timedelta(minutes=mid)).astimezone(tz).utcoffset() == target:
            hi = mid
        else:
            lo = mid + 1
    return low + timedelta(minutes=lo)
