// The islands' transport (M6C, ADR-026 D9): plain relative same-origin
// fetches to `/api/v1/public/…`.
//
// In production the reverse proxy serves the API on the tenant origin,
// so a relative fetch is same-origin by construction and carries
// `Sec-Fetch-Site: same-origin` — the browser-context check's first
// branch. In development the same relative path reaches the dev-only
// forwarder, which preserves Host and the browser-context evidence
// verbatim. No island imports the api-client runtime — the generated
// types are compile-time only, so the client bundle carries none of it.

import type {
  OrderPlace,
  OrderPlacedResponse,
  PublicOrderView,
  PublicPickupSlots,
} from '@restaurant-engine/api-client';

/** One public API outcome, honest about transport failure (`status: null`). */
export type PublicApiResult<T> =
  | { ok: true; data: T }
  | {
      ok: false;
      status: number | null;
      code: string | null;
      details: Record<string, unknown> | null;
    };

async function publicFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<PublicApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { accept: 'application/json', ...init?.headers },
      cache: 'no-store',
    });
  } catch {
    return { ok: false, status: null, code: null, details: null };
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // A body-less or non-JSON answer; the status alone decides below.
  }
  if (response.ok) {
    return { ok: true, data: body as T };
  }
  const error =
    typeof body === 'object' && body !== null
      ? ((body as Record<string, unknown>)['error'] as
          Record<string, unknown> | undefined)
      : undefined;
  return {
    ok: false,
    status: response.status,
    code:
      typeof error?.['code'] === 'string' ? (error['code'] as string) : null,
    details:
      typeof error?.['details'] === 'object' && error['details'] !== null
        ? (error['details'] as Record<string, unknown>)
        : null,
  };
}

export function placeOrder(
  payload: OrderPlace,
): Promise<PublicApiResult<OrderPlacedResponse>> {
  return publicFetch('/api/v1/public/orders', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getPickupSlots(): Promise<PublicApiResult<PublicPickupSlots>> {
  return publicFetch('/api/v1/public/pickup-slots');
}

export function getOrder(
  trackingToken: string,
): Promise<PublicApiResult<PublicOrderView>> {
  return publicFetch(
    `/api/v1/public/orders/${encodeURIComponent(trackingToken)}`,
  );
}

export function cancelOrder(
  trackingToken: string,
): Promise<PublicApiResult<PublicOrderView>> {
  return publicFetch(
    `/api/v1/public/orders/${encodeURIComponent(trackingToken)}/cancel`,
    { method: 'POST' },
  );
}
