// Timestamp presentation for storefront status facts (ADR-022 §9). The
// presentation locale is explicitly 'en-US' — the product's English-first
// presentation, matching the storefront renderer's money formatting.
const dateTime = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}
