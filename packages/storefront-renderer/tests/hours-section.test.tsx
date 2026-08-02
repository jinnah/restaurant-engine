import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import {
  DAY_NAMES,
  formatExceptionDate,
  formatInterval,
  formatMinute,
  weeklyRows,
} from '../src/sections/hours-format';
import { hoursDataFixture, hoursSection } from '../src/fixtures';

// The hours section (M5D, ADR-025 D5): presentation choices from the
// published section, schedule and instant facts from the availability
// composition. Every fixture instant is fixed UTC, so nothing here reads
// the wall clock — the "open now" answer is the server's, only formatted.

describe('hours formatting helpers', () => {
  test('formatMinute covers midnight, noon, and the D1 next-day range', () => {
    expect(formatMinute(0)).toBe('12:00 AM');
    expect(formatMinute(540)).toBe('9:00 AM');
    expect(formatMinute(720)).toBe('12:00 PM');
    expect(formatMinute(1020)).toBe('5:00 PM');
    expect(formatMinute(1439)).toBe('11:59 PM');
    // At and above 1440 the value is the following local day (D1); the
    // wall time wraps, the conventional overnight presentation.
    expect(formatMinute(1440)).toBe('12:00 AM');
    expect(formatMinute(1560)).toBe('2:00 AM');
  });

  test('formatInterval renders an overnight interval end-to-end', () => {
    expect(formatInterval({ opens_minute: 1020, closes_minute: 1560 })).toBe(
      '5:00 PM – 2:00 AM',
    );
  });

  test('weeklyRows lists all seven ISO days, Monday first, gaps closed', () => {
    const rows = weeklyRows(hoursDataFixture().weekly);
    expect(rows.map((row) => row.day)).toEqual([...DAY_NAMES]);
    // The fixture has no Monday service: an absent day is an honest
    // "Closed", never an omitted row.
    expect(rows[0]).toEqual({ day: 'Monday', hours: 'Closed' });
    // Split service joins in opening order.
    expect(rows[1]).toEqual({
      day: 'Tuesday',
      hours: '11:00 AM – 2:00 PM, 5:00 PM – 9:00 PM',
    });
    expect(rows[5]).toEqual({ day: 'Saturday', hours: '5:00 PM – 2:00 AM' });
  });

  test('weeklyRows sorts intervals delivered out of order', () => {
    const rows = weeklyRows([
      { day_of_week: 2, opens_minute: 1020, closes_minute: 1260 },
      { day_of_week: 2, opens_minute: 660, closes_minute: 840 },
    ]);
    expect(rows[2]?.hours).toBe('11:00 AM – 2:00 PM, 5:00 PM – 9:00 PM');
  });

  test('an empty weekly schedule is honestly closed all week', () => {
    for (const row of weeklyRows([])) {
      expect(row.hours).toBe('Closed');
    }
  });

  test('formatExceptionDate is a calendar-date formatting, timezone-free', () => {
    // A date is a calendar fact in the tenant's local calendar; no
    // timezone conversion may ever shift it by a day.
    expect(formatExceptionDate('2026-12-25')).toBe('December 25, 2026');
    expect(formatExceptionDate('2026-01-01')).toBe('January 1, 2026');
  });
});

describe('hours section rendering', () => {
  test('renders heading, intro, live status, weekly schedule, and exceptions', () => {
    render(
      <SectionList
        sections={[hoursSection()]}
        hoursData={hoursDataFixture()}
      />,
    );
    expect(
      screen.getByRole('heading', { level: 2, name: 'Opening hours' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Kitchen closes 30 minutes early.'),
    ).toBeInTheDocument();
    // Open, with the closing instant formatted in the TENANT zone:
    // 2026-08-08T01:00:00Z is 9:00 PM in America/New_York (EDT).
    expect(screen.getByText('Open now')).toBeInTheDocument();
    expect(screen.getByText(/closes 9:00 PM/)).toBeInTheDocument();
    // The weekly schedule as day/times pairs. "Closed" appears twice by
    // design: Monday's weekly row and the December 25 exception.
    expect(screen.getByText('Monday')).toBeInTheDocument();
    expect(screen.getAllByText('Closed')).toHaveLength(2);
    expect(screen.getByText('5:00 PM – 2:00 AM')).toBeInTheDocument();
    // Upcoming exceptions with the D6 note as plain text.
    expect(
      screen.getByRole('heading', { level: 3, name: 'Special hours' }),
    ).toBeInTheDocument();
    expect(screen.getByText('November 26, 2026')).toBeInTheDocument();
    expect(screen.getByText('12:00 PM – 4:00 PM')).toBeInTheDocument();
    expect(screen.getByText(/Thanksgiving — limited menu/)).toBeInTheDocument();
    expect(screen.getByText('December 25, 2026')).toBeInTheDocument();
  });

  test('closed status states the next opening in the tenant zone', () => {
    render(
      <SectionList
        sections={[hoursSection()]}
        hoursData={hoursDataFixture({
          is_open_now: false,
          closes_at: null,
          // Friday 2026-08-07 17:00 EDT = 21:00 UTC.
          next_opens_at: '2026-08-07T21:00:00Z',
        })}
      />,
    );
    expect(screen.getByText('Closed now')).toBeInTheDocument();
    expect(screen.getByText(/opens Friday.*5:00 PM/)).toBeInTheDocument();
  });

  test('a business with nothing upcoming states only "Closed now"', () => {
    render(
      <SectionList
        sections={[hoursSection()]}
        hoursData={hoursDataFixture({
          is_open_now: false,
          closes_at: null,
          next_opens_at: null,
          weekly: [],
          exceptions: [],
        })}
      />,
    );
    expect(screen.getByText('Closed now')).toBeInTheDocument();
    expect(screen.queryByText(/opens/)).not.toBeInTheDocument();
    // Nothing upcoming, nothing fabricated: no special-hours block.
    expect(screen.queryByText('Special hours')).not.toBeInTheDocument();
  });

  test('the owner can turn the status line off; the schedule stays', () => {
    render(
      <SectionList
        sections={[hoursSection({ show_open_now: false })]}
        hoursData={hoursDataFixture()}
      />,
    );
    expect(screen.queryByText('Open now')).not.toBeInTheDocument();
    expect(screen.getByText('Monday')).toBeInTheDocument();
  });

  test('without availability data only the authored copy renders', () => {
    // The MenuSection degradation precedent: the workspace preview passes
    // no availability composition, so the section shows its copy alone.
    render(<SectionList sections={[hoursSection()]} />);
    expect(
      screen.getByRole('heading', { level: 2, name: 'Opening hours' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Open now')).not.toBeInTheDocument();
    expect(screen.queryByText('Monday')).not.toBeInTheDocument();
  });

  test('authored copy and notes render as text, never as markup', () => {
    const { container } = render(
      <SectionList
        sections={[hoursSection({ intro: '<b>bold?</b>' })]}
        hoursData={hoursDataFixture({
          exceptions: [
            {
              exception_date: '2026-12-31',
              intervals: [],
              note: '<script>alert(1)</script>',
            },
          ],
        })}
      />,
    );
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText('<b>bold?</b>')).toBeInTheDocument();
  });
});
