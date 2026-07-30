// @vitest-environment node

// Exact minor-unit presentation (ADR-021): money identity is proved by
// exact strings — 1250 must render as exactly $12.50 — and the conversion
// is digit placement, never a float (the M3E precedent).

import { describe, expect, test } from 'vitest';

import { formatMinorUnits, minorUnitsToDecimalString } from '../src/money';

describe('minorUnitsToDecimalString', () => {
  test('places digits exactly', () => {
    expect(minorUnitsToDecimalString(1250, 2)).toBe('12.50');
    expect(minorUnitsToDecimalString(5, 2)).toBe('0.05');
    expect(minorUnitsToDecimalString(0, 2)).toBe('0.00');
    expect(minorUnitsToDecimalString(100, 2)).toBe('1.00');
    expect(minorUnitsToDecimalString(10_000_000, 2)).toBe('100000.00');
    expect(minorUnitsToDecimalString(1250, 0)).toBe('1250');
    expect(minorUnitsToDecimalString(1250, 3)).toBe('1.250');
  });

  test('a value float division would corrupt stays exact', () => {
    // 1234567 / 100 is not exactly representable in binary floating point;
    // digit placement never goes near it.
    expect(minorUnitsToDecimalString(1_234_567, 2)).toBe('12345.67');
  });

  test('rejects negatives and non-integers', () => {
    expect(() => minorUnitsToDecimalString(-1, 2)).toThrow(/nonnegative/);
    expect(() => minorUnitsToDecimalString(12.5, 2)).toThrow(/integer/);
  });
});

describe('formatMinorUnits', () => {
  test('formats tenant-currency prices in the en-US presentation locale', () => {
    expect(formatMinorUnits(1250, 'USD')).toBe('$12.50');
    expect(formatMinorUnits(0, 'USD')).toBe('$0.00');
    expect(formatMinorUnits(5, 'USD')).toBe('$0.05');
    expect(formatMinorUnits(10_000_000, 'USD')).toBe('$100,000.00');
  });

  test('respects zero-decimal currencies', () => {
    expect(formatMinorUnits(1250, 'JPY')).toBe('¥1,250');
  });
});
