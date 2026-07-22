// Money entry and display (M3E, ADR-018 ruling 8). The input path must never
// multiply: 0.1 * 100 is 10.000000000000002, and a price one minor unit wrong
// is a defect, not a rounding curiosity.

import { describe, expect, test } from 'vitest';
import {
  formatMinor,
  fractionDigits,
  minorToMajorInput,
  moneyErrorMessage,
  parseMajorToMinor,
} from '../src/menu/money';

// The value the backend ceiling happens to sit at today. It is referenced
// only to prove this module does NOT stop there — nothing here may treat it
// as a bound, which is why it is not imported from application code.
const FORMER_FRONTEND_CEILING = 10_000_000;

function minor(input: string, currency = 'USD'): number | string {
  const result = parseMajorToMinor(input, currency);
  return result.ok ? result.minor : result.error;
}

describe('fraction digits come from the currency, never a hardcoded 2', () => {
  test('two-decimal, zero-decimal, and three-decimal currencies', () => {
    expect(fractionDigits('USD')).toBe(2);
    expect(fractionDigits('JPY')).toBe(0);
    expect(fractionDigits('BHD')).toBe(3);
  });
});

describe('parsing two-decimal currencies', () => {
  test('ordinary values', () => {
    expect(minor('12.50')).toBe(1250);
    expect(minor('12.5')).toBe(1250);
    expect(minor('12')).toBe(1200);
    expect(minor('0')).toBe(0);
    expect(minor('0.00')).toBe(0);
  });

  test('0.10 is exactly 10 minor units', () => {
    // The case that catches a float multiply: 0.1 * 100 === 10.000000000000002.
    expect(minor('0.10')).toBe(10);
    expect(minor('0.1')).toBe(10);
    expect(minor('0.01')).toBe(1);
  });

  test('surrounding whitespace and leading zeros are tolerated', () => {
    expect(minor('  12.50  ')).toBe(1250);
    expect(minor('007.50')).toBe(750);
  });

  test('a trailing dot is unambiguous and accepted', () => {
    expect(minor('12.')).toBe(1200);
  });
});

describe('parsing a zero-decimal currency', () => {
  test('whole numbers pass and any decimal is refused', () => {
    expect(minor('1250', 'JPY')).toBe(1250);
    expect(minor('12.5', 'JPY')).toBe('wholeOnly');
    expect(minor('12.0', 'JPY')).toBe('wholeOnly');
  });
});

describe('parsing a three-decimal currency', () => {
  test('three places are exact and a fourth is refused', () => {
    expect(minor('1.234', 'BHD')).toBe(1234);
    expect(minor('1.2', 'BHD')).toBe(1200);
    expect(minor('1.2345', 'BHD')).toBe('tooPrecise');
  });
});

describe('representability, the only bound this module owns', () => {
  test('a price above the former frontend ceiling parses instead of failing', () => {
    // The ceiling is the server's, and it is not published in any form this
    // app can check, so nothing here may refuse a value on its behalf.
    expect(minor('100000.00')).toBe(FORMER_FRONTEND_CEILING);
    expect(minor('100000.01')).toBe(FORMER_FRONTEND_CEILING + 1);
    expect(minor('999999.99')).toBe(99_999_999);
  });

  test('the largest exactly representable integer is accepted', () => {
    expect(minor('90071992547409.91')).toBe(Number.MAX_SAFE_INTEGER);
  });

  test('one minor unit beyond exact representability is refused', () => {
    // Not a policy: past MAX_SAFE_INTEGER the digits cannot be carried
    // exactly, so no faithful price_minor could be sent at all.
    expect(minor('90071992547409.92')).toBe('unsafe');
    expect(minor('999999999999999999.99')).toBe('unsafe');
  });

  test('no message states a maximum price', () => {
    // Naming a ceiling in prose would reintroduce the copied limit by another
    // route. "at most 2 decimal places" is deliberately not caught: precision
    // is a property of the currency, not a bound on the amount.
    for (const error of [
      'unsafe',
      'tooPrecise',
      'wholeOnly',
      'negative',
      'malformed',
      'required',
    ] as const) {
      expect(moneyErrorMessage(error, 'USD')).not.toMatch(
        /maximum|higher than|this system allows|too (large|high|big)/i,
      );
    }
  });
});

describe('rejections', () => {
  test('excess precision', () => {
    expect(minor('1.234')).toBe('tooPrecise');
  });

  test('negative values are named as such, not called malformed', () => {
    expect(minor('-1')).toBe('negative');
    expect(minor('-0.01')).toBe('negative');
  });

  test('malformed input', () => {
    expect(minor('abc')).toBe('malformed');
    expect(minor('1,50')).toBe('malformed'); // grouping/comma decimal is out of syntax
    expect(minor('1.2.3')).toBe('malformed');
    expect(minor('.')).toBe('malformed');
    expect(minor('$12.50')).toBe('malformed');
    expect(minor('1 000')).toBe('malformed');
  });

  test('an empty value is distinguished from a malformed one', () => {
    expect(minor('')).toBe('required');
    expect(minor('   ')).toBe('required');
  });
});

describe('Bengali–Indic digits', () => {
  test('are normalized to ASCII before parsing', () => {
    expect(minor('১২.৫০')).toBe(1250);
    expect(minor('০.১০')).toBe(10);
    expect(minor('১২৫০', 'JPY')).toBe(1250);
  });
});

describe('display and round trips', () => {
  test('the editable form is plain and matches the accepted syntax', () => {
    expect(minorToMajorInput(1250, 'USD')).toBe('12.50');
    expect(minorToMajorInput(10, 'USD')).toBe('0.10');
    expect(minorToMajorInput(0, 'USD')).toBe('0.00');
    expect(minorToMajorInput(1250, 'JPY')).toBe('1250');
    expect(minorToMajorInput(1234, 'BHD')).toBe('1.234');
    expect(minorToMajorInput(FORMER_FRONTEND_CEILING, 'USD')).toBe('100000.00');
  });

  test('every stored integer round-trips through the editable form', () => {
    const values = [
      0,
      1,
      9,
      10,
      99,
      100,
      350,
      1250,
      999999,
      FORMER_FRONTEND_CEILING,
      // Above the old ceiling, and at the edge of exact representability:
      // both must survive the round trip untouched.
      FORMER_FRONTEND_CEILING + 1,
      Number.MAX_SAFE_INTEGER,
    ];
    for (const currency of ['USD', 'JPY', 'BHD']) {
      for (const value of values) {
        expect(minor(minorToMajorInput(value, currency), currency)).toBe(value);
      }
    }
  });

  test('currency formatting carries the right symbol and precision', () => {
    expect(formatMinor(1250, 'USD')).toContain('12.50');
    expect(formatMinor(0, 'USD')).toContain('0.00');
    expect(formatMinor(10, 'USD')).toContain('0.10');
    expect(formatMinor(FORMER_FRONTEND_CEILING, 'USD')).toContain('100,000.00');
    // A zero-decimal currency must not gain decimals.
    expect(formatMinor(1250, 'JPY')).not.toContain('.');
    expect(formatMinor(1234, 'BHD')).toContain('1.234');
  });

  test('formatting is exact across the whole permitted range', () => {
    // Division is safe here where multiplication was not: a minor integer
    // over its own exponent never produces a further decimal place, so there
    // is no rounding boundary to land on.
    for (let value = 0; value <= 2000; value += 1) {
      expect(formatMinor(value, 'USD')).toContain(
        minorToMajorInput(value, 'USD'),
      );
    }
  });
});
