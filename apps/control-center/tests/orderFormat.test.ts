// The board's pure presentation helpers (M7C, ADR-027) at frozen times:
// order age, the overdue rule, and the two zone-aware renderings. Money
// is deliberately not restated here — the control center has one
// minor-unit formatter, tested with the menu.

import { describe, expect, test } from 'vitest';
import {
  businessDay,
  formatClock,
  formatInstant,
  isOverdue,
  orderAge,
  STATUS_LABELS,
} from '../src/orders/orderFormat';
import { adminOrderSummary } from './support/mockClient';

const ZONE = 'America/New_York';

describe('instants in the business zone', () => {
  test('an instant renders in the business zone, not the device zone', () => {
    expect(formatInstant('2026-08-07T15:30:00Z', ZONE)).toBe('Aug 7, 11:30 AM');
    expect(formatClock('2026-08-07T15:30:00Z', ZONE)).toBe('11:30 AM');
    // The same instant, a different restaurant.
    expect(formatClock('2026-08-07T15:30:00Z', 'America/Los_Angeles')).toBe(
      '8:30 AM',
    );
  });

  test('the business day is the date the restaurant is living in', () => {
    // 02:30 UTC is still the previous evening in New York.
    expect(businessDay(new Date('2026-08-08T02:30:00Z'), ZONE)).toBe(
      '2026-08-07',
    );
    expect(businessDay(new Date('2026-08-08T12:00:00Z'), ZONE)).toBe(
      '2026-08-08',
    );
  });
});

describe('order age', () => {
  const now = new Date('2026-08-07T15:30:00Z');

  test('reads the way a counter would say it', () => {
    expect(orderAge('2026-08-07T15:29:30Z', now)).toBe('just now');
    expect(orderAge('2026-08-07T15:26:00Z', now)).toBe('4m');
    expect(orderAge('2026-08-07T14:18:00Z', now)).toBe('1h 12m');
  });

  test('a clock skew never renders a negative age', () => {
    expect(orderAge('2026-08-07T15:31:00Z', now)).toBe('just now');
  });
});

describe('the overdue rule', () => {
  const now = new Date('2026-08-07T15:30:00Z');
  const late = { promised_pickup_at: '2026-08-07T15:00:00Z' };
  const soon = { promised_pickup_at: '2026-08-07T16:00:00Z' };

  test('a late order the kitchen still owes work for is overdue', () => {
    for (const status of ['submitted', 'accepted', 'preparing'] as const) {
      expect(isOverdue(adminOrderSummary({ status, ...late }), now)).toBe(true);
    }
  });

  test('nothing is overdue before its promise', () => {
    expect(
      isOverdue(adminOrderSummary({ status: 'preparing', ...soon }), now),
    ).toBe(false);
  });

  test('ready and terminal orders owe nothing more', () => {
    for (const status of [
      'ready',
      'completed',
      'rejected',
      'cancelled',
    ] as const) {
      expect(isOverdue(adminOrderSummary({ status, ...late }), now)).toBe(
        false,
      );
    }
  });

  test('the kitchen own estimate replaces the promise once set', () => {
    const order = adminOrderSummary({
      status: 'preparing',
      promised_pickup_at: '2026-08-07T15:00:00Z',
      estimated_ready_at: '2026-08-07T15:45:00Z',
    });
    // Late against the promise, but the kitchen said 15:45 and it is 15:30.
    expect(isOverdue(order, now)).toBe(false);
    expect(isOverdue(order, new Date('2026-08-07T15:46:00Z'))).toBe(true);
  });
});

test('every status has operational language, none leaks the wire value', () => {
  expect(Object.values(STATUS_LABELS)).toEqual([
    'New',
    'Accepted',
    'Preparing',
    'Ready',
    'Completed',
    'Declined',
    'Cancelled',
  ]);
});
