import type {
  AdminOrderSummary,
  OrderStatus,
} from '@restaurant-engine/api-client';

/**
 * Pure presentation helpers for the order board (M7C, ADR-027). Every
 * function takes its instants as arguments — the components own the one
 * ticking clock — so all of this is testable at frozen times.
 *
 * Nothing here does timezone *arithmetic*: `Intl` renders an instant in a
 * zone, which is a lookup, not a DST calculation. Anything that needs a
 * zone boundary (the operational day) is the server's to compute — the
 * list endpoint's `day` filter.
 *
 * Money is deliberately absent: the control center already has one
 * minor-unit formatter with its own reasoned float argument
 * (`menu/money.ts`), and a second copy is how two surfaces start
 * disagreeing about a price.
 */

const PRESENTATION_LOCALE = 'en-US';

/** "Aug 3, 5:30 PM" — one UTC instant shown in the business timezone. */
export function formatInstant(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(PRESENTATION_LOCALE, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
  }).format(new Date(iso));
}

/** "5:30 PM" — the same instant when the day is already established. */
export function formatClock(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(PRESENTATION_LOCALE, {
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
  }).format(new Date(iso));
}

/**
 * The business's own calendar date for an instant, as `YYYY-MM-DD` — the
 * shape the list endpoint's `day` filter takes. `en-CA` is ISO-ordered by
 * definition, so this is a format, never a computation.
 */
export function businessDay(now: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone,
  }).format(now);
}

/** "just now" / "4m" / "1h 12m" — how long ago the order arrived. */
export function orderAge(placedAtIso: string, now: Date): string {
  const seconds = Math.max(
    0,
    Math.floor((now.getTime() - new Date(placedAtIso).getTime()) / 1000),
  );
  if (seconds < 60) {
    return 'just now';
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${String(minutes)}m`;
  }
  return `${String(Math.floor(minutes / 60))}h ${String(minutes % 60)}m`;
}

// The states a kitchen still owes work for — the only ones that can be
// overdue. Ready and the terminal states owe the customer nothing new.
const OVERDUE_STATUSES: readonly OrderStatus[] = [
  'submitted',
  'accepted',
  'preparing',
];

/**
 * Overdue: the kitchen's own estimate (or, absent one, the promise) has
 * passed while the order still needs work (ADR-027 §5's indicator).
 */
export function isOverdue(order: AdminOrderSummary, now: Date): boolean {
  if (!OVERDUE_STATUSES.includes(order.status)) {
    return false;
  }
  const deadline = order.estimated_ready_at ?? order.promised_pickup_at;
  return now.getTime() > new Date(deadline).getTime();
}

/**
 * The board's operational vocabulary (docs/08: "New", never the wire
 * value "submitted"). Keyed by the generated status union, so a status
 * added to the machine fails the type check here rather than rendering
 * a raw enum value at a counter (blueprint §3.7: display-only mappings
 * backed by generated values).
 */
export const STATUS_LABELS: Record<OrderStatus, string> = {
  submitted: 'New',
  accepted: 'Accepted',
  preparing: 'Preparing',
  ready: 'Ready',
  completed: 'Completed',
  rejected: 'Declined',
  cancelled: 'Cancelled',
};
