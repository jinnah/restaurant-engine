// Order operations facade (M7A, ADR-027).
//
// The business-scoped operational surface: the board list (filters,
// search, the exclusive order-number cursor), the full detail with the status
// timeline, today's metrics, the named member transition commands
// (D1/D4 — status is never patched), and the prep estimate (D7). Every
// operation rides the caller's membership and the D2
// `business.orders.operate` capability; this surface carries customer
// PII by design, which is why its authority is named.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type AdminOrderSummary = components['schemas']['AdminOrderSummary'];
export type AdminOrderList = components['schemas']['AdminOrderList'];
export type AdminOrderDetail = components['schemas']['AdminOrderDetail'];
export type StatusEventView = components['schemas']['StatusEventView'];
export type OrderEstimateSet = components['schemas']['OrderEstimateSet'];
export type OrderMetrics = components['schemas']['OrderMetrics'];
export type PopularItem = components['schemas']['PopularItem'];
export type OrderStatus = components['schemas']['OrderStatus'];

const CSRF_HEADER = 'X-CSRF-Token';

export interface OrderListParams {
  status?: OrderStatus[];
  /** A tenant-local calendar date (`YYYY-MM-DD`), resolved server-side. */
  day?: string;
  placed_after?: string;
  placed_before?: string;
  q?: string;
  before_number?: number;
  limit?: number;
}

export interface OrdersApi {
  /** One newest-first page: filters, search, exclusive id cursor (D6). */
  list(
    businessId: string,
    params?: OrderListParams,
  ): Promise<ApiResult<AdminOrderList>>;
  /** The full operational projection with the status timeline (D6). */
  get(
    businessId: string,
    orderId: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
  /** Today's operational metrics, computed live (D11). */
  metrics(businessId: string): Promise<ApiResult<OrderMetrics>>;
  /** Accept a submitted order (D1). */
  accept(
    businessId: string,
    orderId: string,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
  /** Reject a submitted order; its pickup slot is released (D1/D3). */
  reject(
    businessId: string,
    orderId: string,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
  /** Move an accepted order to preparing (D1). */
  startPreparing(
    businessId: string,
    orderId: string,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
  /** Mark a preparing order ready for pickup (D1). */
  markReady(
    businessId: string,
    orderId: string,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
  /** Complete a ready order at pickup (D1). */
  complete(
    businessId: string,
    orderId: string,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
  /** Cancel a submitted order as a member (D4); the slot is released. */
  cancel(
    businessId: string,
    orderId: string,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
  /** Set or clear the prep estimate while accepted/preparing (D7). */
  setEstimate(
    businessId: string,
    orderId: string,
    body: OrderEstimateSet,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>>;
}

type TransitionPath =
  | '/api/v1/businesses/{business_id}/orders/{order_id}/accept'
  | '/api/v1/businesses/{business_id}/orders/{order_id}/reject'
  | '/api/v1/businesses/{business_id}/orders/{order_id}/start-preparing'
  | '/api/v1/businesses/{business_id}/orders/{order_id}/mark-ready'
  | '/api/v1/businesses/{business_id}/orders/{order_id}/complete'
  | '/api/v1/businesses/{business_id}/orders/{order_id}/cancel';

export function createOrdersApi(client: Client<paths>): OrdersApi {
  const csrf = (csrfToken: string) => ({ [CSRF_HEADER]: csrfToken });
  const orderPath = (businessId: string, orderId: string) => ({
    params: { path: { business_id: businessId, order_id: orderId } },
  });
  const transition = async (
    path: TransitionPath,
    businessId: string,
    orderId: string,
    csrfToken: string,
  ): Promise<ApiResult<AdminOrderDetail>> => {
    try {
      const { data, error, response } = await client.POST(path, {
        ...orderPath(businessId, orderId),
        headers: csrf(csrfToken),
      });
      return toResult(data, error, response);
    } catch {
      return { ok: false, status: null, envelope: null };
    }
  };

  return {
    async list(businessId, params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/orders',
          {
            params: {
              path: { business_id: businessId },
              query: params,
            },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async get(businessId, orderId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/orders/{order_id}',
          orderPath(businessId, orderId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async metrics(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/orders/metrics',
          { params: { path: { business_id: businessId } } },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    accept: (businessId, orderId, csrfToken) =>
      transition(
        '/api/v1/businesses/{business_id}/orders/{order_id}/accept',
        businessId,
        orderId,
        csrfToken,
      ),
    reject: (businessId, orderId, csrfToken) =>
      transition(
        '/api/v1/businesses/{business_id}/orders/{order_id}/reject',
        businessId,
        orderId,
        csrfToken,
      ),
    startPreparing: (businessId, orderId, csrfToken) =>
      transition(
        '/api/v1/businesses/{business_id}/orders/{order_id}/start-preparing',
        businessId,
        orderId,
        csrfToken,
      ),
    markReady: (businessId, orderId, csrfToken) =>
      transition(
        '/api/v1/businesses/{business_id}/orders/{order_id}/mark-ready',
        businessId,
        orderId,
        csrfToken,
      ),
    complete: (businessId, orderId, csrfToken) =>
      transition(
        '/api/v1/businesses/{business_id}/orders/{order_id}/complete',
        businessId,
        orderId,
        csrfToken,
      ),
    cancel: (businessId, orderId, csrfToken) =>
      transition(
        '/api/v1/businesses/{business_id}/orders/{order_id}/cancel',
        businessId,
        orderId,
        csrfToken,
      ),

    async setEstimate(businessId, orderId, body, csrfToken) {
      try {
        const { data, error, response } = await client.PUT(
          '/api/v1/businesses/{business_id}/orders/{order_id}/estimate',
          {
            ...orderPath(businessId, orderId),
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
