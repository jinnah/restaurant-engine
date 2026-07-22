import { MAX_PRICE_MINOR_DISPLAY } from './policy';

/**
 * Money entry and display (ADR-018 ruling 8).
 *
 * Prices are integer minor units on the wire and in the database; the
 * currency belongs to the Business, never to an item (ADR-017 D8). Two rules
 * govern everything here:
 *
 * 1. **No floating-point arithmetic on the input path.** `12.50` becomes
 *    1250 by padding the fractional part and concatenating digit strings,
 *    never by multiplying by 100 — `0.1 * 100` is 10.000000000000002, and a
 *    price that is one minor unit wrong is a real defect, not a rounding
 *    curiosity.
 * 2. **Fraction digits come from the currency**, via
 *    `Intl.NumberFormat(...).resolvedOptions()`. USD has two, JPY has none,
 *    BHD has three. Assuming two would silently corrupt the others.
 *
 * Input syntax is deliberately locale-fixed: ASCII digits, an optional dot
 * separator, nothing else. `Intl` formats but does not parse, and
 * hand-rolling locale-aware parsing (comma decimals, grouping separators)
 * is a correctness hazard with no dependency budget behind it. The one
 * concession is Bengali–Indic digits, normalized to ASCII, because that is
 * the launch market (blueprint §2.1) and a fixed ten-codepoint map is a
 * transliteration, not a parser.
 */

export type MoneyParseError =
  | 'required'
  | 'malformed'
  | 'negative'
  | 'tooPrecise'
  | 'wholeOnly'
  | 'tooLarge';

export type MoneyParseResult =
  { ok: true; minor: number } | { ok: false; error: MoneyParseError };

const BENGALI_ZERO = 0x09e6; // ০
const SYNTAX = /^[0-9]*\.?[0-9]*$/;

/** The currency's minor-unit exponent, from the runtime's own currency data. */
export function fractionDigits(currency: string): number {
  try {
    // `maximumFractionDigits` is optional in the DOM typings but is always
    // resolved for style: 'currency'; the fallback keeps that assumption
    // from becoming an undefined leaking into arithmetic.
    return (
      new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
      }).resolvedOptions().maximumFractionDigits ?? 2
    );
  } catch {
    // Unreachable in practice: a Business currency is validated as a
    // three-letter code at creation, and an unknown-but-well-formed code
    // resolves to two digits rather than throwing.
    return 2;
  }
}

function normalizeDigits(value: string): string {
  let out = '';
  for (const character of value) {
    const code = character.codePointAt(0) ?? 0;
    out +=
      code >= BENGALI_ZERO && code <= BENGALI_ZERO + 9
        ? String(code - BENGALI_ZERO)
        : character;
  }
  return out;
}

/**
 * Convert typed major units to integer minor units, or say precisely why it
 * cannot be done. The server revalidates and its 422 wins.
 */
export function parseMajorToMinor(
  raw: string,
  currency: string,
): MoneyParseResult {
  const digits = fractionDigits(currency);
  const value = normalizeDigits(raw).trim();

  if (value === '') {
    return { ok: false, error: 'required' };
  }
  // A sign is reported as its own problem: "not a number" would be unhelpful
  // when the user typed a perfectly good number with a minus in front.
  if (value.startsWith('-')) {
    return { ok: false, error: 'negative' };
  }
  if (!SYNTAX.test(value)) {
    return { ok: false, error: 'malformed' };
  }

  const [intPart = '', fracPart = ''] = value.split('.');
  if (intPart === '' && fracPart === '') {
    return { ok: false, error: 'malformed' };
  }
  if (fracPart.length > digits) {
    return { ok: false, error: digits === 0 ? 'wholeOnly' : 'tooPrecise' };
  }

  // Digit-string concatenation: exact by construction, no multiplication.
  const minorDigits =
    (intPart === '' ? '0' : intPart) + fracPart.padEnd(digits, '0');
  const minor = Number(minorDigits);
  if (!Number.isSafeInteger(minor) || minor > MAX_PRICE_MINOR_DISPLAY) {
    return { ok: false, error: 'tooLarge' };
  }
  return { ok: true, minor };
}

/** Message for a parse failure, phrased for the person who typed it. */
export function moneyErrorMessage(
  error: MoneyParseError,
  currency: string,
): string {
  const digits = fractionDigits(currency);
  switch (error) {
    case 'required':
      return 'Enter a price.';
    case 'negative':
      return 'A price cannot be negative.';
    case 'wholeOnly':
      return `${currency} prices are whole numbers — leave out the decimal point.`;
    case 'tooPrecise':
      return `Use at most ${String(digits)} decimal places.`;
    case 'tooLarge':
      return 'That price is higher than this system allows.';
    case 'malformed':
      return 'Enter a price using digits and a dot, for example 12.50.';
  }
}

/**
 * The plain editable form of a stored integer: `1250` → `"12.50"`. Built by
 * string padding so it round-trips exactly through `parseMajorToMinor`, and
 * deliberately not localized — the input accepts one syntax, so it must show
 * that syntax back.
 */
export function minorToMajorInput(minor: number, currency: string): string {
  const digits = fractionDigits(currency);
  const text = String(Math.trunc(Math.abs(minor)));
  if (digits === 0) {
    return text;
  }
  const padded = text.padStart(digits + 1, '0');
  return `${padded.slice(0, -digits)}.${padded.slice(-digits)}`;
}

/**
 * Currency-formatted display of a stored integer: `1250` in USD → `$12.50`.
 *
 * The division here is safe where the input path's multiplication would not
 * be: `minor / 10 ** digits` has at most eight significant digits for every
 * value the contract permits, so its double representation is within ~1e-13
 * of the true value, while `Intl` rounds at `digits` — and because a minor
 * integer divided by its own exponent never produces a further decimal
 * place, there is no rounding boundary to land on.
 */
export function formatMinor(minor: number, currency: string): string {
  const digits = fractionDigits(currency);
  const formatter = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
  });
  return formatter.format(minor / 10 ** digits);
}
