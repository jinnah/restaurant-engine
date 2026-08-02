// Wall-time helpers for the hours workspace (M5C, ADR-025).
//
// The API speaks the D1 minute encoding (minutes from local midnight;
// closes above 1440 end on the following local day); the editor speaks
// `<input type="time">` values plus an explicit "next day" choice. These
// helpers convert between the two and answer the one timezone question
// the editor asks — "does this wall time exist on that date?" — so a
// spring-forward gap is flagged where it is authored instead of shifting
// silently (the server rule moves it to the gap's end; ADR-025 rule 3).
//
// Everything here is presentation support. The server's pure timekeeping
// core remains the authority on every instant.

export const DAY_NAMES = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

export const MINUTES_PER_DAY = 1440;

/** "HH:MM" for a same-day minute value (the input control's value). */
export function minuteToTimeInput(minute: number): string {
  const clamped =
    ((minute % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  const hours = String(Math.floor(clamped / 60)).padStart(2, '0');
  const minutes = String(clamped % 60).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/** Minutes from midnight for an "HH:MM" input value; null when unparsable. */
export function timeInputToMinute(value: string): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (match === null) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) {
    return null;
  }
  return hours * 60 + minutes;
}

/** A friendly clock label ("2:30 AM") for copy; the inputs stay 24-hour. */
export function minuteLabel(minute: number): string {
  const clamped =
    ((minute % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  const hours24 = Math.floor(clamped / 60);
  const minutes = clamped % 60;
  const hours12 = hours24 % 12 === 0 ? 12 : hours24 % 12;
  const suffix = hours24 < 12 ? 'AM' : 'PM';
  return `${hours12}:${String(minutes).padStart(2, '0')} ${suffix}`;
}

function tzOffsetMinutes(epochMs: number, timeZone: string): number {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone,
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
      .formatToParts(new Date(epochMs))
      .map((part) => [part.type, part.value]),
  );
  const asUtc = Date.UTC(
    Number(parts['year']),
    Number(parts['month']) - 1,
    Number(parts['day']),
    // Some ICU builds render midnight as "24" in hour-cycle h23 edge cases.
    Number(parts['hour']) % 24,
    Number(parts['minute']),
    Number(parts['second']),
  );
  return (asUtc - epochMs) / 60_000;
}

/**
 * Whether `minute` on the local date `isoDate` (YYYY-MM-DD) exists in
 * `timeZone`. A wall time inside a spring-forward gap does not: the
 * offset round-trip cannot reproduce it. Ambiguous (fall-back) times
 * exist and return true — they are not gaps.
 */
export function wallTimeExists(
  isoDate: string,
  minute: number,
  timeZone: string,
): boolean {
  const [year, month, day] = isoDate.split('-').map(Number);
  if (year === undefined || month === undefined || day === undefined) {
    return true; // unparsable dates are the caller's validation problem
  }
  const wallUtc = Date.UTC(
    year,
    month - 1,
    day + Math.floor(minute / MINUTES_PER_DAY),
    Math.floor((minute % MINUTES_PER_DAY) / 60),
    minute % 60,
  );
  let epoch = wallUtc;
  for (let i = 0; i < 2; i += 1) {
    epoch = wallUtc - tzOffsetMinutes(epoch, timeZone) * 60_000;
  }
  return epoch + tzOffsetMinutes(epoch, timeZone) * 60_000 === wallUtc;
}

/** The next `count` ISO dates falling on `dayOfWeek` (0 = Monday), from today. */
export function upcomingDatesForWeekday(
  dayOfWeek: number,
  count: number,
  from = new Date(),
): string[] {
  const dates: string[] = [];
  const cursor = new Date(
    Date.UTC(from.getFullYear(), from.getMonth(), from.getDate()),
  );
  // JS getUTCDay: 0 = Sunday; the D1 encoding: 0 = Monday.
  const target = (dayOfWeek + 1) % 7;
  while (dates.length < count) {
    if (cursor.getUTCDay() === target) {
      dates.push(cursor.toISOString().slice(0, 10));
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

/**
 * The first upcoming date (ISO) on which a weekly boundary falls inside a
 * DST gap, scanning a year of that weekday — or null. Only boundaries in
 * the small hours can be affected (real transitions happen around
 * 00:00–04:00 local), so callers cheaply skip the scan for daytime values.
 */
export function firstWeeklyGapDate(
  dayOfWeek: number,
  minute: number,
  timeZone: string,
  from = new Date(),
): string | null {
  if (minute % MINUTES_PER_DAY >= 5 * 60) {
    return null; // no real-world transition touches 05:00+
  }
  for (const isoDate of upcomingDatesForWeekday(dayOfWeek, 53, from)) {
    if (!wallTimeExists(isoDate, minute, timeZone)) {
      return isoDate;
    }
  }
  return null;
}

/** Human date ("Mar 8, 2026") for warning copy. */
export function isoDateLabel(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  if (year === undefined || month === undefined || day === undefined) {
    return isoDate;
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)));
}
