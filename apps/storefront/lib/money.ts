// Exact minor-unit money presentation (ADR-021).
//
// Prices arrive as integer minor units with the tenant's currency
// (blueprint: integer money everywhere; client totals are display hints).
// The integer is converted to a decimal *string* by digit placement and
// handed to Intl.NumberFormat as a string — numeric string inputs are
// formatted from their mathematical value, so no floating-point
// conversion ever occurs. The presentation locale is explicitly 'en-US'
// (the product's English-first presentation); the currency symbol and
// fraction digits come from the tenant currency.

const PRESENTATION_LOCALE = 'en-US';

export function minorUnitsToDecimalString(
  minor: number,
  fractionDigits: number,
): string {
  if (!Number.isSafeInteger(minor) || minor < 0) {
    throw new Error('minor units must be a nonnegative safe integer');
  }
  if (fractionDigits === 0) {
    return String(minor);
  }
  const digits = String(minor).padStart(fractionDigits + 1, '0');
  return `${digits.slice(0, -fractionDigits)}.${digits.slice(-fractionDigits)}`;
}

export function formatMinorUnits(minor: number, currency: string): string {
  const formatter = new Intl.NumberFormat(PRESENTATION_LOCALE, {
    style: 'currency',
    currency,
  });
  const fractionDigits = formatter.resolvedOptions().maximumFractionDigits ?? 2;
  return formatter.format(
    // Intl formats numeric strings exactly; the digit string never passes
    // through a float.
    minorUnitsToDecimalString(minor, fractionDigits) as unknown as number,
  );
}
