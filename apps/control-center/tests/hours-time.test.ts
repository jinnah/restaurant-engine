// Pure wall-time helpers for the hours workspace (M5C). The DST facts
// asserted here are real tzdata facts: America/New_York springs forward
// on 2026-03-08 (02:00–02:59 does not exist) and falls back on
// 2026-11-01 (01:00–01:59 happens twice); America/Phoenix observes no
// DST at all.

import { describe, expect, test } from 'vitest';
import {
  firstWeeklyGapDate,
  isoDateLabel,
  minuteLabel,
  minuteToTimeInput,
  timeInputToMinute,
  upcomingDatesForWeekday,
  wallTimeExists,
} from '../src/hours/time';

describe('minute <-> time input', () => {
  test('renders the boundary minutes of the day', () => {
    expect(minuteToTimeInput(0)).toBe('00:00');
    expect(minuteToTimeInput(1439)).toBe('23:59');
    expect(minuteToTimeInput(1020)).toBe('17:00');
  });

  test('an overnight closes value renders as its wall time', () => {
    // 1560 = 02:00 on the following day (D1 encoding).
    expect(minuteToTimeInput(1560)).toBe('02:00');
  });

  test('round-trips every input the control can produce', () => {
    expect(timeInputToMinute('00:00')).toBe(0);
    expect(timeInputToMinute('23:59')).toBe(1439);
    expect(timeInputToMinute(minuteToTimeInput(789))).toBe(789);
  });

  test('rejects values outside the 24-hour clock and junk', () => {
    expect(timeInputToMinute('24:00')).toBeNull();
    expect(timeInputToMinute('12:60')).toBeNull();
    expect(timeInputToMinute('9:30')).toBeNull(); // controls emit two digits
    expect(timeInputToMinute('')).toBeNull();
  });
});

describe('minuteLabel', () => {
  test('renders 12-hour clock labels with correct noon and midnight', () => {
    expect(minuteLabel(0)).toBe('12:00 AM');
    expect(minuteLabel(150)).toBe('2:30 AM');
    expect(minuteLabel(720)).toBe('12:00 PM');
    expect(minuteLabel(1290)).toBe('9:30 PM');
  });

  test('an encoded overnight minute labels as its wall time', () => {
    expect(minuteLabel(1560)).toBe('2:00 AM');
  });
});

describe('wallTimeExists', () => {
  test('every minute inside the New York spring-forward gap is missing', () => {
    for (let minute = 120; minute < 180; minute += 1) {
      expect(
        wallTimeExists('2026-03-08', minute, 'America/New_York'),
        `minute ${String(minute)}`,
      ).toBe(false);
    }
  });

  test('the minutes bracketing the gap exist', () => {
    expect(wallTimeExists('2026-03-08', 60, 'America/New_York')).toBe(true);
    expect(wallTimeExists('2026-03-08', 180, 'America/New_York')).toBe(true);
  });

  test('fall-back ambiguity is not a gap', () => {
    // 01:30 on 2026-11-01 happens twice in New York; it exists.
    expect(wallTimeExists('2026-11-01', 90, 'America/New_York')).toBe(true);
  });

  test('a zone without DST has no gaps', () => {
    expect(wallTimeExists('2026-03-08', 150, 'America/Phoenix')).toBe(true);
  });

  test('an encoded overnight minute is checked on the following day', () => {
    // 02:30 encoded from the previous day (150 + 1440) lands on the
    // transition date itself when the base date is the day before.
    expect(wallTimeExists('2026-03-07', 1590, 'America/New_York')).toBe(false);
    expect(wallTimeExists('2026-03-08', 1590, 'America/New_York')).toBe(true);
  });
});

describe('upcomingDatesForWeekday', () => {
  test('returns only the requested weekday, from the given date inclusive', () => {
    // 2026-03-01 is a Sunday (D1 day 6).
    expect(
      upcomingDatesForWeekday(6, 3, new Date(Date.UTC(2026, 2, 1))),
    ).toEqual(['2026-03-01', '2026-03-08', '2026-03-15']);
  });

  test('Monday is day 0 (ISO 8601), not JavaScript Sunday', () => {
    expect(
      upcomingDatesForWeekday(0, 2, new Date(Date.UTC(2026, 2, 1))),
    ).toEqual(['2026-03-02', '2026-03-09']);
  });
});

describe('firstWeeklyGapDate', () => {
  test('finds the spring-forward Sunday for a small-hours boundary', () => {
    expect(
      firstWeeklyGapDate(
        6,
        150,
        'America/New_York',
        new Date(Date.UTC(2026, 2, 1)),
      ),
    ).toBe('2026-03-08');
  });

  test('daytime boundaries never scan into a gap', () => {
    expect(
      firstWeeklyGapDate(
        6,
        600,
        'America/New_York',
        new Date(Date.UTC(2026, 2, 1)),
      ),
    ).toBeNull();
  });

  test('a zone without DST yields no gap date', () => {
    expect(
      firstWeeklyGapDate(
        6,
        150,
        'America/Phoenix',
        new Date(Date.UTC(2026, 2, 1)),
      ),
    ).toBeNull();
  });

  test('a weekday the transition never lands on yields no gap date', () => {
    // United States transitions happen on Sundays; Wednesday 02:30 is safe.
    expect(
      firstWeeklyGapDate(
        2,
        150,
        'America/New_York',
        new Date(Date.UTC(2026, 2, 1)),
      ),
    ).toBeNull();
  });
});

describe('isoDateLabel', () => {
  test('renders the short human date used by warning copy', () => {
    expect(isoDateLabel('2026-03-08')).toBe('Mar 8, 2026');
    expect(isoDateLabel('2026-12-25')).toBe('Dec 25, 2026');
  });
});
