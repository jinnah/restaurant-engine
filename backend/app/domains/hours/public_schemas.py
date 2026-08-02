"""Public availability projection schemas (M5B, ADR-025).

Deliberately **separate** from the administrative schemas (the M3D/M4C
convention): the admin shapes carry management facts (`is_configured`,
the full fulfillment policy values, the backward exception window) that
an unauthenticated consumer has no business seeing. Only
`PublicSiteSummary` is shared, because it is already the public Business
projection — the same single source of name, slug, timezone, and
currency every public surface uses.

Times keep the D1 minute encoding (`closes_minute` above 1440 ends the
interval on the following local day) plus the tenant timezone: the
consumer formats wall times; the projection's computed facts
(`is_open_now`, `closes_at`, `next_opens_at`, `next_pickup_at`) are UTC
instants derived through the pure core, so "public availability derives
from structured settings" (the Milestone 5 exit criterion) is literal.
"""

from datetime import date, datetime

from pydantic import BaseModel

from app.domains.businesses.schemas import PublicSiteSummary


class PublicHoursInterval(BaseModel):
    """One open interval in D1 minutes on its local day."""

    opens_minute: int
    closes_minute: int


class PublicWeeklyInterval(PublicHoursInterval):
    """One recurring interval (ISO day: 0 = Monday … 6 = Sunday)."""

    day_of_week: int


class PublicScheduleException(BaseModel):
    """One upcoming override: special hours, or closed all day.

    ``intervals`` empty = closed all day. ``note`` is the owner's
    customer-visible label (ruling D6), already normalized plain text.
    """

    exception_date: date
    intervals: list[PublicHoursInterval]
    note: str | None


class PublicPickup(BaseModel):
    """The pickup facts a visitor may see before ordering exists (M6).

    Deliberately minimal: whether pickup is offered, whether "as soon as
    possible" is offered, and the earliest valid pickup instant. Lead
    times, slot intervals, and cut-offs are operational configuration and
    stay off the public surface until checkout (M6) needs them.
    """

    enabled: bool
    asap_enabled: bool
    next_pickup_at: datetime | None


class PublicAvailability(BaseModel):
    """The structured hours of the host-resolved active Business.

    Every active business has one — a business with no configured hours
    is honestly closed with nothing upcoming, not a 404, because absence
    of a schedule is a real operational state the storefront must render.
    `exceptions` is the bounded forward window only (today onward in the
    tenant's local calendar); past overrides are history, not display.
    """

    business: PublicSiteSummary
    is_open_now: bool
    closes_at: datetime | None
    next_opens_at: datetime | None
    weekly: list[PublicWeeklyInterval]
    exceptions: list[PublicScheduleException]
    pickup: PublicPickup
