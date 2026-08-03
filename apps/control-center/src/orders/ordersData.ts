import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import type {
  AdminOrderDetail,
  AdminOrderList,
  OrderEstimateSet,
  OrderingPauseSet,
  OrderListParams,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { asApiFailure } from '../api/failure';
import { requireCsrf, unwrapPrivileged } from '../api/failures';
import type { FormFailure } from '../components/formErrors';
import { hoursKeys } from '../hours/keys';
import { ordersKeys, type OrderListFilters } from './keys';

/**
 * The board's polling cadence (ADR-027 ruling D9): short polling through
 * TanStack's own interval — the §14.3 doctrine's first consumer. The
 * library's default leaves background tabs unpolled, which is exactly
 * the ruling.
 */
export const BOARD_POLL_MS = 10_000;
const METRICS_POLL_MS = 60_000;

/**
 * A search spans every status (an order someone asks about by name is
 * rarely still "New"), which is also ruling D6's customer-linked order
 * history; the status chips narrow the board, not the search.
 */
function listParams(filters: OrderListFilters): OrderListParams {
  const params: OrderListParams = {};
  if (filters.q === '') {
    if (filters.statuses.length > 0) {
      params.status = [...filters.statuses];
    }
  } else {
    params.q = filters.q;
  }
  if (filters.day !== '') {
    params.day = filters.day;
  }
  return params;
}

/**
 * The board's rows: newest first, one page at a time behind the D6
 * exclusive order-number cursor, so "load more" is real history rather
 * than a silently truncated first page.
 *
 * The live board polls; a dated or searched view does not — that is
 * someone reading history, and re-fetching every loaded page under them
 * every ten seconds would be noise, not freshness.
 */
export function useOrdersList(businessId: string, filters: OrderListFilters) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const live = filters.day === '' && filters.q === '';
  return useInfiniteQuery({
    queryKey: ordersKeys.list(businessId, filters),
    queryFn: async ({ pageParam }) =>
      unwrapPrivileged(
        queryClient,
        await client.orders.list(businessId, {
          ...listParams(filters),
          ...(pageParam === null ? {} : { before_number: pageParam }),
        }),
      ),
    initialPageParam: null as number | null,
    getNextPageParam: (last: AdminOrderList) => last.next_before_number,
    refetchInterval: live ? BOARD_POLL_MS : false,
  });
}

/**
 * The incoming-order watch (ruling D10). Deliberately independent of the
 * board's filters: staff must never miss an order because they were
 * reading yesterday's history or the Ready column. It is also the
 * honest source of the "New" count.
 */
export function useIncomingOrders(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ordersKeys.incoming(businessId),
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.orders.list(businessId, { status: ['submitted'] }),
      ),
    refetchInterval: BOARD_POLL_MS,
  });
}

/** The full operational projection with the timeline, while open. */
export function useOrderDetail(businessId: string, orderId: string | null) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ordersKeys.detail(businessId, orderId ?? 'none'),
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.orders.get(businessId, orderId ?? ''),
      ),
    enabled: orderId !== null,
    refetchInterval: BOARD_POLL_MS,
  });
}

/** Today's computed metrics (ruling D11), refreshed at a calmer pace. */
export function useOrderMetrics(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ordersKeys.metrics(businessId),
    queryFn: async () =>
      unwrapPrivileged(queryClient, await client.orders.metrics(businessId)),
    refetchInterval: METRICS_POLL_MS,
  });
}

/** The six named member commands (rulings D1/D4), one mutation each. */
export type OrderCommand =
  'accept' | 'reject' | 'startPreparing' | 'markReady' | 'complete' | 'cancel';

export function useOrderCommand(businessId: string, command: OrderCommand) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (orderId: string): Promise<AdminOrderDetail> =>
      unwrapPrivileged(
        queryClient,
        await client.orders[command](
          businessId,
          orderId,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (detail) => {
      queryClient.setQueryData(
        ordersKeys.detail(businessId, detail.id),
        detail,
      );
      void queryClient.invalidateQueries({
        queryKey: ordersKeys.lists(businessId),
      });
      void queryClient.invalidateQueries({
        queryKey: ordersKeys.incoming(businessId),
      });
      void queryClient.invalidateQueries({
        queryKey: ordersKeys.metrics(businessId),
      });
    },
    onError: () => {
      // A raced or illegal command (D1): the truth is on the server —
      // refetch everything this board shows rather than guessing.
      void queryClient.invalidateQueries({
        queryKey: ordersKeys.root(businessId),
      });
    },
  });
}

/** Set or clear the prep estimate (ruling D7). */
export function useSetEstimate(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { orderId: string; body: OrderEstimateSet }) =>
      unwrapPrivileged(
        queryClient,
        await client.orders.setEstimate(
          businessId,
          input.orderId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (detail) => {
      queryClient.setQueryData(
        ordersKeys.detail(businessId, detail.id),
        detail,
      );
      void queryClient.invalidateQueries({
        queryKey: ordersKeys.lists(businessId),
      });
    },
    onError: () => {
      void queryClient.invalidateQueries({
        queryKey: ordersKeys.root(businessId),
      });
    },
  });
}

/**
 * Pause or resume ordering (ruling D8) — the hours-owned command, so
 * success writes the returned settings document into the hours cache
 * the fulfillment panel reads too.
 */
export function useSetOrderingPause(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: OrderingPauseSet) =>
      unwrapPrivileged(
        queryClient,
        await client.hours.setOrderingPause(
          businessId,
          body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (settings) => {
      queryClient.setQueryData(hoursKeys.settings(businessId), settings);
    },
  });
}

/** A failed order mutation as one honest sentence (the hours pattern). */
export function ordersFailure(error: unknown, fallback: string): FormFailure {
  const failure = asApiFailure(error);
  const messages = [failure.envelope?.error.message ?? fallback];
  for (const fieldError of failure.envelope?.error.field_errors ?? []) {
    messages.push(fieldError.message);
  }
  return { summary: messages.join(' '), fields: {} };
}

/** True when the failure is the D1 race: the order changed elsewhere. */
export function isInvalidState(error: unknown): boolean {
  return asApiFailure(error).envelope?.error.code === 'invalid_state';
}
