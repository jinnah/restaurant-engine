// Restaurant-scoped member facade (M2B).
//
// The caller reads their own restaurant; the server authorizes via
// membership. Nonmembers get 404 (existence non-disclosure).

import type { Client } from 'openapi-fetch';

import type { paths } from './generated/schema';
import type { RestaurantSummary } from './platform';
import { toResult, type ApiResult } from './result';

export interface RestaurantsApi {
  get(restaurantId: string): Promise<ApiResult<RestaurantSummary>>;
}

export function createRestaurantsApi(client: Client<paths>): RestaurantsApi {
  return {
    async get(restaurantId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/restaurants/{restaurant_id}',
          { params: { path: { restaurant_id: restaurantId } } },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
