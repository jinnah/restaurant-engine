// Pure presentation helpers for the hours section (M5D, ADR-025 D5).
//
// The projection speaks the D1 minute encoding (minutes from local
// midnight; `closes_minute` above 1440 ends the interval on the following
// local day) plus UTC instants for the computed facts. Everything here is
// a pure function of those values: no ambient clock, no network, no
// framework import — the renderer never re-derives an "open now" answer,
// it only formats the one the availability projection computed.
//
// Labels and formats are neutral English product chrome (the "View the
// full menu" convention); tenant copy stays the owner's authored text.

import type {
  PublicScheduleException,
  PublicWeeklyInterval,
} from '../contract';

/** ISO day names, indexed by the contract's `day_of_week` (0 = Monday). */
export const DAY_NAMES = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

/**
 * One D1 minute value as a 12-hour wall time ("9:00 AM", "11:59 PM").
 * Values at or above 1440 are the following local day and wrap to their
 * wall time — "17:00–02:00" reads as evening service past midnight, the
 * conventional restaurant presentation.
 */
export function formatMinute(minute: number): string {
  const hour24 = Math.floor(minute / 60) % 24;
  const minutes = minute % 60;
  const period = hour24 < 12 ? 'AM' : 'PM';
  const hour12 = hour24 % 12 === 0 ? 12 : hour24 % 12;
  return `${String(hour12)}:${String(minutes).padStart(2, '0')} ${period}`;
}

/** One open interval, e.g. "11:00 AM – 9:00 PM". */
export function formatInterval(interval: {
  opens_minute: number;
  closes_minute: number;
}): string {
  return `${formatMinute(interval.opens_minute)} – ${formatMinute(interval.closes_minute)}`;
}

/**
 * The weekly schedule as seven display rows, Monday first (ISO order),
 * every day present: a day without intervals reads "Closed", because an
 * empty schedule is a real operational state the storefront must render
 * honestly rather than hide.
 */
export function weeklyRows(
  weekly: PublicWeeklyInterval[],
): { day: string; hours: string }[] {
  return DAY_NAMES.map((day, index) => {
    const intervals = weekly
      .filter((interval) => interval.day_of_week === index)
      .sort((a, b) => a.opens_minute - b.opens_minute);
    return {
      day,
      hours:
        intervals.length === 0
          ? 'Closed'
          : intervals.map(formatInterval).join(', '),
    };
  });
}

/**
 * An exception's local calendar date ("December 25, 2026"). The contract
 * value is a plain date in the tenant's calendar, so it is formatted as a
 * calendar date — never converted through a timezone, which could shift
 * it by a day.
 */
export function formatExceptionDate(isoDate: string): string {
  // Parsed field-wise rather than through `Date` so no timezone is ever
  // involved in what is, by contract, a timezone-less calendar date.
  const [year, month, day] = isoDate.split('-').map(Number);
  const MONTHS = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];
  const name = MONTHS[(month ?? 1) - 1] ?? '';
  return `${name} ${String(day ?? 1)}, ${String(year ?? 0)}`;
}

/** One exception's hours: special intervals, or "Closed". */
export function formatExceptionHours(
  exception: PublicScheduleException,
): string {
  return exception.intervals.length === 0
    ? 'Closed'
    : exception.intervals.map(formatInterval).join(', ');
}

/**
 * A UTC instant as tenant-local wall time ("9:00 PM"), for the status
 * line's "closes" fact. The tenant timezone is the only bridge — the
 * viewer's locale never reinterprets the instant.
 */
export function formatInstantTime(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso));
}

/**
 * A UTC instant as tenant-local weekday plus wall time
 * ("Friday 5:00 PM"), for the status line's "opens" fact.
 */
export function formatInstantDayTime(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    weekday: 'long',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso));
}
