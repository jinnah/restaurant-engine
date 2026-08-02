"""Public availability assembly (M5B, ADR-025).

Reads the stored schedule under the already-resolved Business and derives
the instant facts through the pure core. The wall clock enters exactly
once, here, as the injected default for ``now`` — the computation itself
stays a function of its arguments, which is what keeps the public
projection testable at frozen instants.

The response is deliberately computed per request and never cached
(ruling D4): a sixty-second grant would make "Open now" wrong for up to
a minute at exactly the boundaries a customer checks, so the route keeps
the global ``no-store`` default and ``cache_control.py`` is untouched.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.domains.businesses.resolution import ResolvedBusiness
from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.hours import policies, repository
from app.domains.hours.availability import ExceptionDay, availability_at
from app.domains.hours.public_schemas import (
    PublicAvailability,
    PublicHoursInterval,
    PublicPickup,
    PublicScheduleException,
    PublicWeeklyInterval,
)
from app.domains.hours.service import DEFAULT_POLICY, effective_policy
from app.domains.hours.timekeeping import local_date

# How far forward the public projection lists exceptions. Bounded and
# short: visitors plan days ahead, not the whole editable window the
# administrative read exposes (policies.EXCEPTION_FUTURE_WINDOW_DAYS).
PUBLIC_EXCEPTION_WINDOW_DAYS = 60


def assemble_availability(
    db: Session, business: ResolvedBusiness, *, now: datetime | None = None
) -> PublicAvailability:
    """The public availability of an already-resolved active Business."""
    if now is None:
        now = datetime.now(UTC)
    tz = ZoneInfo(business.timezone)
    today = local_date(now, tz)

    weekly_rows = repository.list_weekly(db, business_id=business.business_id)
    weekly_by_day: dict[int, list[tuple[int, int]]] = {}
    for row in weekly_rows:
        weekly_by_day.setdefault(row.day_of_week, []).append((row.opens_minute, row.closes_minute))

    # One read serves both needs: the availability computation wants
    # yesterday onward (an overnight interval that began the previous
    # local date is still live), the display window is today onward.
    exception_rows = repository.list_exceptions(
        db,
        business_id=business.business_id,
        start=today - timedelta(days=1),
        end=today + timedelta(days=policies.EXCEPTION_FUTURE_WINDOW_DAYS),
    )
    grouped: dict[date, list[tuple[int, int]]] = {}
    notes: dict[date, str | None] = {}
    for exception_row in exception_rows:
        grouped.setdefault(exception_row.exception_date, [])
        if exception_row.opens_minute is not None and exception_row.closes_minute is not None:
            grouped[exception_row.exception_date].append(
                (exception_row.opens_minute, exception_row.closes_minute)
            )
        notes.setdefault(exception_row.exception_date, exception_row.note)
    exceptions = {
        day: ExceptionDay(exception_date=day, intervals=tuple(sorted(intervals)), note=notes[day])
        for day, intervals in grouped.items()
    }

    policy = effective_policy(db, business.business_id)
    facts = availability_at(now, weekly=weekly_by_day, exceptions=exceptions, policy=policy, tz=tz)
    return PublicAvailability(
        business=PublicSiteSummary(
            name=business.name,
            slug=business.slug,
            timezone=business.timezone,
            currency=business.currency,
        ),
        is_open_now=facts.is_open_now,
        closes_at=facts.closes_at,
        next_opens_at=facts.next_opens_at,
        weekly=[
            PublicWeeklyInterval(
                day_of_week=row.day_of_week,
                opens_minute=row.opens_minute,
                closes_minute=row.closes_minute,
            )
            for row in weekly_rows
        ],
        exceptions=[
            PublicScheduleException(
                exception_date=day,
                intervals=[
                    PublicHoursInterval(opens_minute=opens, closes_minute=closes)
                    for opens, closes in exceptions[day].intervals
                ],
                note=exceptions[day].note,
            )
            for day in sorted(exceptions)
            if today <= day <= today + timedelta(days=PUBLIC_EXCEPTION_WINDOW_DAYS)
        ],
        pickup=PublicPickup(
            enabled=policy.pickup_enabled,
            asap_enabled=policy.asap_enabled,
            next_pickup_at=facts.next_pickup_at,
        ),
    )


# Re-exported so a reviewer finds the default beside the projection that
# applies it; the values live in ``hours.policies``.
__all__ = ["DEFAULT_POLICY", "PUBLIC_EXCEPTION_WINDOW_DAYS", "assemble_availability"]
