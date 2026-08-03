"""Hours application service (M5A, ADR-025).

Owns every hours transaction. Authorization is enforced here (M2B
discipline): reads require ``business.view`` (ruling D7 — the schedule is
public information and staff see the hours they work); writes require
``business.hours.write`` and follow the established preamble — membership
capability check, then ``SELECT … FOR UPDATE`` on the Business row, which
serializes per-tenant hours writes and pins the lifecycle status (closed
businesses stay readable and refuse every mutation with 409
``invalid_state``).

Both write commands are exact full-set replacements validated as pure
functions before any database work, and the exact no-op is suppressed:
resubmitting the stored configuration writes nothing and audits nothing.

The wall clock enters exactly twice, both times as a tenant-local *date*
(the exception window and the read window); everything else takes ``now``
as an argument through the pure ``availability`` module.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.errors import (
    ApiError,
    ErrorCode,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import (
    BusinessHoursUpdatedDetails,
    FulfillmentUpdatedDetails,
    OrderingPauseSetDetails,
    ScheduleExceptionRemovedDetails,
    ScheduleExceptionSetDetails,
)
from app.domains.businesses import repository as businesses_repository
from app.domains.businesses.lifecycle import BusinessStatus
from app.domains.businesses.models import Business
from app.domains.hours import policies, repository
from app.domains.hours.availability import (
    ExceptionDay,
    FulfillmentPolicy,
    availability_at,
)
from app.domains.hours.models import FulfillmentSettings, ScheduleException
from app.domains.hours.schemas import (
    AvailabilityPreview,
    FulfillmentOut,
    FulfillmentSet,
    HoursInterval,
    HoursSettings,
    OrderingPauseSet,
    ScheduleExceptionOut,
    ScheduleExceptionSet,
    WeeklyIntervalOut,
    WeeklyScheduleSet,
)
from app.domains.hours.timekeeping import local_date
from app.domains.identity.actor import ActorContext
from app.domains.identity.authorization import require_membership_capability
from app.domains.identity.policies import Capability

DEFAULT_POLICY = FulfillmentPolicy(
    pickup_enabled=policies.DEFAULT_PICKUP_ENABLED,
    asap_enabled=policies.DEFAULT_ASAP_ENABLED,
    lead_time_minutes=policies.DEFAULT_LEAD_TIME_MINUTES,
    slot_interval_minutes=policies.DEFAULT_SLOT_INTERVAL_MINUTES,
    last_order_before_close_minutes=policies.DEFAULT_LAST_ORDER_MINUTES,
    max_days_ahead=policies.DEFAULT_MAX_DAYS_AHEAD,
)


def _authorize_read(db: Session, actor: ActorContext, business_id: uuid.UUID) -> Business:
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_VIEW
    )
    business = businesses_repository.get(db, business_id)
    if business is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    return business


def _authorize_write(db: Session, actor: ActorContext, business_id: uuid.UUID) -> Business:
    """Capability, business lock, and lifecycle — the write preamble.

    Returns the **locked** Business row (the deterministic first lock,
    serializing per-tenant hours writes), so callers read the timezone
    from the same pinned row they mutate under.
    """
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_HOURS_WRITE
    )
    business = businesses_repository.get_for_update(db, business_id)
    if business is None:  # pragma: no cover - membership implies existence via FK
        raise ResourceNotFoundError("Business not found.")
    if business.status == BusinessStatus.CLOSED.value:
        raise InvalidStateError("cannot modify the hours of a closed business")
    return business


# --- Projection helpers ------------------------------------------------------


def _exceptions_out(rows: list[ScheduleException]) -> list[ScheduleExceptionOut]:
    """Group stored rows into one override per date.

    A NULL-interval row is the closed-all-day marker; interval rows carry
    the date's special hours. The service writes each date as one exact
    set, so mixed dates cannot exist through the product; reads are
    defensive anyway and let intervals win (fail toward showing hours).
    """
    by_date: dict[date, list[ScheduleException]] = {}
    for row in rows:
        by_date.setdefault(row.exception_date, []).append(row)
    out: list[ScheduleExceptionOut] = []
    for exception_date in sorted(by_date):
        day_rows = by_date[exception_date]
        intervals = [
            HoursInterval(opens_minute=row.opens_minute, closes_minute=row.closes_minute)
            for row in day_rows
            if row.opens_minute is not None and row.closes_minute is not None
        ]
        out.append(
            ScheduleExceptionOut(
                exception_date=exception_date,
                intervals=sorted(intervals, key=lambda i: (i.opens_minute, i.closes_minute)),
                note=day_rows[0].note,
            )
        )
    return out


def _fulfillment_out(row: FulfillmentSettings | None) -> FulfillmentOut:
    if row is None:
        return FulfillmentOut(
            pickup_enabled=DEFAULT_POLICY.pickup_enabled,
            asap_enabled=DEFAULT_POLICY.asap_enabled,
            lead_time_minutes=DEFAULT_POLICY.lead_time_minutes,
            slot_interval_minutes=DEFAULT_POLICY.slot_interval_minutes,
            last_order_before_close_minutes=DEFAULT_POLICY.last_order_before_close_minutes,
            max_days_ahead=DEFAULT_POLICY.max_days_ahead,
            max_orders_per_slot=DEFAULT_POLICY.max_orders_per_slot,
            ordering_paused=DEFAULT_POLICY.ordering_paused,
            pause_note=DEFAULT_POLICY.pause_note,
            pause_resume_at=DEFAULT_POLICY.pause_resume_at,
            is_configured=False,
        )
    return FulfillmentOut(
        pickup_enabled=row.pickup_enabled,
        asap_enabled=row.asap_enabled,
        lead_time_minutes=row.lead_time_minutes,
        slot_interval_minutes=row.slot_interval_minutes,
        last_order_before_close_minutes=row.last_order_before_close_minutes,
        max_days_ahead=row.max_days_ahead,
        max_orders_per_slot=row.max_orders_per_slot,
        ordering_paused=row.ordering_paused,
        pause_note=row.pause_note,
        pause_resume_at=row.pause_resume_at,
        is_configured=True,
    )


def _settings_view(db: Session, business: Business) -> HoursSettings:
    tz = ZoneInfo(business.timezone)
    today = local_date(datetime.now(UTC), tz)
    weekly = repository.list_weekly(db, business_id=business.id)
    exceptions = repository.list_exceptions(
        db,
        business_id=business.id,
        start=today - timedelta(days=policies.EXCEPTION_PAST_WINDOW_DAYS),
        end=today + timedelta(days=policies.EXCEPTION_FUTURE_WINDOW_DAYS),
    )
    return HoursSettings(
        timezone=business.timezone,
        weekly=[
            WeeklyIntervalOut(
                day_of_week=row.day_of_week,
                opens_minute=row.opens_minute,
                closes_minute=row.closes_minute,
            )
            for row in weekly
        ],
        exceptions=_exceptions_out(exceptions),
        fulfillment=_fulfillment_out(repository.get_fulfillment(db, business_id=business.id)),
    )


def _domain_inputs(
    db: Session, business: Business
) -> tuple[dict[int, list[tuple[int, int]]], dict[date, ExceptionDay]]:
    weekly: dict[int, list[tuple[int, int]]] = {}
    for row in repository.list_weekly(db, business_id=business.id):
        weekly.setdefault(row.day_of_week, []).append((row.opens_minute, row.closes_minute))
    exceptions: dict[date, ExceptionDay] = {}
    for out in _exceptions_out(
        repository.list_exceptions(
            db,
            business_id=business.id,
            # The availability scan starts one day back and runs to the
            # bounded horizon; matching window here keeps inputs complete.
            start=local_date(datetime.now(UTC), ZoneInfo(business.timezone))
            - timedelta(days=policies.EXCEPTION_PAST_WINDOW_DAYS),
            end=local_date(datetime.now(UTC), ZoneInfo(business.timezone))
            + timedelta(days=policies.EXCEPTION_FUTURE_WINDOW_DAYS),
        )
    ):
        exceptions[out.exception_date] = ExceptionDay(
            exception_date=out.exception_date,
            intervals=tuple(
                (interval.opens_minute, interval.closes_minute) for interval in out.intervals
            ),
            note=out.note,
        )
    return weekly, exceptions


def effective_policy(db: Session, business_id: uuid.UUID) -> FulfillmentPolicy:
    """The stored fulfillment policy, or the registry defaults (M5A).

    Shared with the public projection (M5B): both surfaces must derive
    from the same effective settings, so the fallback lives once.
    """
    row = repository.get_fulfillment(db, business_id=business_id)
    if row is None:
        return DEFAULT_POLICY
    return FulfillmentPolicy(
        pickup_enabled=row.pickup_enabled,
        asap_enabled=row.asap_enabled,
        lead_time_minutes=row.lead_time_minutes,
        slot_interval_minutes=row.slot_interval_minutes,
        last_order_before_close_minutes=row.last_order_before_close_minutes,
        max_days_ahead=row.max_days_ahead,
        max_orders_per_slot=row.max_orders_per_slot,
        ordering_paused=row.ordering_paused,
        pause_note=row.pause_note,
        pause_resume_at=row.pause_resume_at,
    )


# --- Reads -------------------------------------------------------------------


def get_hours(db: Session, actor: ActorContext, business_id: uuid.UUID) -> HoursSettings:
    """The complete operating configuration in one read."""
    business = _authorize_read(db, actor, business_id)
    return _settings_view(db, business)


def preview_availability(
    db: Session, actor: ActorContext, business_id: uuid.UUID, at: datetime | None
) -> AvailabilityPreview:
    """The computed facts at ``at`` (default: now) — the member probe.

    Lets an owner check a DST weekend or a holiday before it happens, and
    gives the E2E suite a deterministic instant to assert against.
    """
    business = _authorize_read(db, actor, business_id)
    if at is None:
        at = datetime.now(UTC)
    elif at.tzinfo is None:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "at must be a timezone-aware instant (for example 2026-03-08T07:00:00Z)",
        )
    weekly, exceptions = _domain_inputs(db, business)
    facts = availability_at(
        at,
        weekly=weekly,
        exceptions=exceptions,
        policy=effective_policy(db, business_id),
        tz=ZoneInfo(business.timezone),
    )
    return AvailabilityPreview(
        at=at.astimezone(UTC),
        timezone=business.timezone,
        is_open_now=facts.is_open_now,
        closes_at=facts.closes_at,
        next_opens_at=facts.next_opens_at,
        next_pickup_at=facts.next_pickup_at,
    )


# --- Commands ----------------------------------------------------------------


def set_weekly_schedule(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: WeeklyScheduleSet
) -> HoursSettings:
    """Replace the whole weekly schedule (idempotent; exact no-op suppressed)."""
    business = _authorize_write(db, actor, business_id)
    submitted = [(i.day_of_week, i.opens_minute, i.closes_minute) for i in payload.intervals]
    stored = [
        (row.day_of_week, row.opens_minute, row.closes_minute)
        for row in repository.list_weekly(db, business_id=business_id)
    ]
    if submitted == stored:
        return _settings_view(db, business)
    repository.replace_weekly(db, business_id=business_id, intervals=submitted)
    recorder.record(
        db,
        AuditAction.BUSINESS_HOURS_UPDATED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="business_hours",
        target_id=str(business_id),
        details=BusinessHoursUpdatedDetails(interval_count=len(submitted)),
    )
    db.commit()
    return _settings_view(db, business)


def _require_in_window(business: Business, exception_date: date) -> None:
    tz = ZoneInfo(business.timezone)
    today = local_date(datetime.now(UTC), tz)
    start = today - timedelta(days=policies.EXCEPTION_PAST_WINDOW_DAYS)
    end = today + timedelta(days=policies.EXCEPTION_FUTURE_WINDOW_DAYS)
    if not (start <= exception_date <= end):
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "exception date is outside the editable window",
            details={
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            },
        )


def set_schedule_exception(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    exception_date: date,
    payload: ScheduleExceptionSet,
) -> HoursSettings:
    """Create or replace one date's override (idempotent per date)."""
    business = _authorize_write(db, actor, business_id)
    _require_in_window(business, exception_date)
    submitted = [(i.opens_minute, i.closes_minute) for i in payload.intervals]
    stored_rows = repository.list_exception_rows_for_date(
        db, business_id=business_id, exception_date=exception_date
    )
    stored = [
        (row.opens_minute, row.closes_minute)
        for row in stored_rows
        if row.opens_minute is not None and row.closes_minute is not None
    ]
    stored_note = stored_rows[0].note if stored_rows else None
    if stored_rows and stored == submitted and stored_note == payload.note:
        return _settings_view(db, business)
    repository.replace_exception(
        db,
        business_id=business_id,
        exception_date=exception_date,
        intervals=submitted,
        note=payload.note,
    )
    recorder.record(
        db,
        AuditAction.BUSINESS_SCHEDULE_EXCEPTION_SET,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="schedule_exception",
        target_id=exception_date.isoformat(),
        details=ScheduleExceptionSetDetails(
            exception_date=exception_date.isoformat(),
            kind="special_hours" if submitted else "closed_all_day",
            interval_count=len(submitted),
            note="present" if payload.note is not None else "absent",
        ),
    )
    db.commit()
    return _settings_view(db, business)


def remove_schedule_exception(
    db: Session, actor: ActorContext, business_id: uuid.UUID, exception_date: date
) -> None:
    """Remove one date's override; absent → 404 (nothing to remove)."""
    _authorize_write(db, actor, business_id)
    removed = repository.delete_exception(
        db, business_id=business_id, exception_date=exception_date
    )
    if removed == 0:
        raise ResourceNotFoundError("Schedule exception not found.")
    recorder.record(
        db,
        AuditAction.BUSINESS_SCHEDULE_EXCEPTION_REMOVED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="schedule_exception",
        target_id=exception_date.isoformat(),
        details=ScheduleExceptionRemovedDetails(exception_date=exception_date.isoformat()),
    )
    db.commit()


def set_fulfillment(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: FulfillmentSet
) -> HoursSettings:
    """Write the full fulfillment policy (materializes the row on first write)."""
    business = _authorize_write(db, actor, business_id)
    row = repository.get_fulfillment(db, business_id=business_id)
    if row is not None and (
        row.pickup_enabled == payload.pickup_enabled
        and row.asap_enabled == payload.asap_enabled
        and row.lead_time_minutes == payload.lead_time_minutes
        and row.slot_interval_minutes == payload.slot_interval_minutes
        and row.last_order_before_close_minutes == payload.last_order_before_close_minutes
        and row.max_days_ahead == payload.max_days_ahead
        and row.max_orders_per_slot == payload.max_orders_per_slot
    ):
        return _settings_view(db, business)
    if row is None:
        row = FulfillmentSettings(
            business_id=business_id,
            pickup_enabled=payload.pickup_enabled,
            asap_enabled=payload.asap_enabled,
            lead_time_minutes=payload.lead_time_minutes,
            slot_interval_minutes=payload.slot_interval_minutes,
            last_order_before_close_minutes=payload.last_order_before_close_minutes,
            max_days_ahead=payload.max_days_ahead,
            max_orders_per_slot=payload.max_orders_per_slot,
        )
        repository.add(db, row)
    else:
        row.pickup_enabled = payload.pickup_enabled
        row.asap_enabled = payload.asap_enabled
        row.lead_time_minutes = payload.lead_time_minutes
        row.slot_interval_minutes = payload.slot_interval_minutes
        row.last_order_before_close_minutes = payload.last_order_before_close_minutes
        row.max_days_ahead = payload.max_days_ahead
        row.max_orders_per_slot = payload.max_orders_per_slot
    recorder.record(
        db,
        AuditAction.BUSINESS_FULFILLMENT_UPDATED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="fulfillment_settings",
        target_id=str(business_id),
        details=FulfillmentUpdatedDetails(
            pickup="enabled" if payload.pickup_enabled else "disabled",
            asap="enabled" if payload.asap_enabled else "disabled",
            lead_time_minutes=payload.lead_time_minutes,
            slot_interval_minutes=payload.slot_interval_minutes,
            last_order_before_close_minutes=payload.last_order_before_close_minutes,
            max_days_ahead=payload.max_days_ahead,
            max_orders_per_slot=payload.max_orders_per_slot,
        ),
    )
    db.commit()
    return _settings_view(db, business)


def set_ordering_pause(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: OrderingPauseSet
) -> HoursSettings:
    """Pause or resume ordering (M7A, ADR-027 ruling D8).

    Its own command, deliberately outside the fulfillment full document
    (the review amendment: an older client's fulfillment save must not
    silently unpause a business). Resuming clears the note and instant;
    the schema already refuses a note or resume time without ``paused``.
    Materializes the settings row from the registry defaults on first
    use, the M4G-A mechanism the other fulfillment write follows.
    """
    business = _authorize_write(db, actor, business_id)
    row = repository.get_fulfillment(db, business_id=business_id)
    if row is not None and (
        row.ordering_paused == payload.paused
        and row.pause_note == payload.note
        and row.pause_resume_at == payload.resume_at
    ):
        return _settings_view(db, business)
    if row is None:
        row = FulfillmentSettings(
            business_id=business_id,
            pickup_enabled=DEFAULT_POLICY.pickup_enabled,
            asap_enabled=DEFAULT_POLICY.asap_enabled,
            lead_time_minutes=DEFAULT_POLICY.lead_time_minutes,
            slot_interval_minutes=DEFAULT_POLICY.slot_interval_minutes,
            last_order_before_close_minutes=DEFAULT_POLICY.last_order_before_close_minutes,
            max_days_ahead=DEFAULT_POLICY.max_days_ahead,
            max_orders_per_slot=DEFAULT_POLICY.max_orders_per_slot,
            ordering_paused=payload.paused,
            pause_note=payload.note,
            pause_resume_at=payload.resume_at,
        )
        repository.add(db, row)
    else:
        row.ordering_paused = payload.paused
        row.pause_note = payload.note
        row.pause_resume_at = payload.resume_at
    recorder.record(
        db,
        AuditAction.BUSINESS_ORDERING_PAUSE_SET,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="fulfillment_settings",
        target_id=str(business_id),
        details=OrderingPauseSetDetails(
            ordering="paused" if payload.paused else "resumed",
            note="present" if payload.note is not None else "absent",
            resume_at=None if payload.resume_at is None else payload.resume_at.isoformat(),
        ),
    )
    db.commit()
    return _settings_view(db, business)
