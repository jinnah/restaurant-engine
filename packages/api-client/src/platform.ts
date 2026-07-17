// Platform restaurant-management facade (M2B).
//
// Every unsafe call sends credentials (the session cookie) via the internal
// client; the CSRF synchronizer token must be passed back explicitly on
// unsafe calls (ADR-010). Lifecycle commands take no data but send an empty
// body so the strict server schema accepts them.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

type GeneratedRestaurantCreate = components['schemas']['RestaurantCreate'];
export type RestaurantSummary = components['schemas']['RestaurantSummary'];
export type RestaurantPage = components['schemas']['RestaurantPage'];

/**
 * Create-restaurant input. `timezone` and `currency` are optional here — the
 * server defaults them (the OpenAPI contract lists only `name`/`slug` as
 * required). openapi-typescript marks default-valued fields as required in
 * the generated type; the facade smooths that idiom in exactly one place
 * (ADR-009) so callers omit what the server fills.
 */
export interface RestaurantCreate {
  name: string;
  slug: string;
  timezone?: string;
  currency?: string;
}

const CSRF_HEADER = 'X-CSRF-Token';

export interface PlatformApi {
  createRestaurant(
    body: RestaurantCreate,
    csrfToken: string,
  ): Promise<ApiResult<RestaurantSummary>>;
  listRestaurants(params?: {
    limit?: number;
    offset?: number;
  }): Promise<ApiResult<RestaurantPage>>;
  getRestaurant(restaurantId: string): Promise<ApiResult<RestaurantSummary>>;
  activate(
    restaurantId: string,
    csrfToken: string,
  ): Promise<ApiResult<RestaurantSummary>>;
  suspend(
    restaurantId: string,
    csrfToken: string,
  ): Promise<ApiResult<RestaurantSummary>>;
  reactivate(
    restaurantId: string,
    csrfToken: string,
  ): Promise<ApiResult<RestaurantSummary>>;
  close(
    restaurantId: string,
    csrfToken: string,
  ): Promise<ApiResult<RestaurantSummary>>;
}

export function createPlatformApi(client: Client<paths>): PlatformApi {
  const csrf = (csrfToken: string) => ({ [CSRF_HEADER]: csrfToken });
  const path = (restaurantId: string) => ({
    params: { path: { restaurant_id: restaurantId } },
  });

  return {
    async createRestaurant(body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/restaurants',
          // The server accepts the partial (required: name, slug); the cast
          // reconciles openapi-typescript's over-strict default handling.
          { body: body as GeneratedRestaurantCreate, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async listRestaurants(params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/platform/restaurants',
          {
            params: { query: { limit: params?.limit, offset: params?.offset } },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getRestaurant(restaurantId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/platform/restaurants/{restaurant_id}',
          path(restaurantId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async activate(restaurantId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/restaurants/{restaurant_id}/activate',
          { ...path(restaurantId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async suspend(restaurantId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/restaurants/{restaurant_id}/suspend',
          { ...path(restaurantId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async reactivate(restaurantId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/restaurants/{restaurant_id}/reactivate',
          { ...path(restaurantId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async close(restaurantId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/restaurants/{restaurant_id}/close',
          { ...path(restaurantId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
