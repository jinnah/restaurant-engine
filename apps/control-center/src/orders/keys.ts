import type { OrderStatus } from '@restaurant-engine/api-client';

/**
 * Query keys for the order board (M7C, ADR-027). The list is keyed by its
 * filter shape (each filter/search/day is its own cache entry, so
 * switching filters never shows another filter's rows), the detail by
 * order id, the new-order watch and the metrics by business alone.
 */
export interface OrderListFilters {
  /** Empty means "any status" — what a search always asks for. */
  statuses: readonly OrderStatus[];
  q: string;
  /** A tenant-local calendar date, or '' for the live (undated) board. */
  day: string;
}

export const ordersKeys = {
  root: (businessId: string) => ['orders', businessId] as const,
  list: (businessId: string, filters: OrderListFilters) =>
    [
      'orders',
      businessId,
      'list',
      filters.statuses.join(','),
      filters.q,
      filters.day,
    ] as const,
  lists: (businessId: string) => ['orders', businessId, 'list'] as const,
  /** The filter-independent watch that makes a new order impossible to miss. */
  incoming: (businessId: string) => ['orders', businessId, 'incoming'] as const,
  detail: (businessId: string, orderId: string) =>
    ['orders', businessId, 'detail', orderId] as const,
  details: (businessId: string) => ['orders', businessId, 'detail'] as const,
  metrics: (businessId: string) => ['orders', businessId, 'metrics'] as const,
};
