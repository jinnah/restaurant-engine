// Instant presentation for the ordering surface (M6C).
//
// Order and slot instants are UTC; the tenant timezone is the only
// correct display zone (the ADR-025 timestamp doctrine). Presentation
// locale is the product's English-first 'en-US', matching the shared
// renderer's money and hours formatting.

const PRESENTATION_LOCALE = 'en-US';

/** "Sat, Aug 8, 5:30 PM" — one instant in the tenant's zone. */
export function formatInstant(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(PRESENTATION_LOCALE, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
  }).format(new Date(iso));
}
