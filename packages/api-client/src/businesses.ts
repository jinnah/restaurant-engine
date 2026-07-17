// Business-scoped member facade (M2B).
//
// The caller reads their own business; the server authorizes via
// membership. Nonmembers get 404 (existence non-disclosure).

import type { Client } from 'openapi-fetch';

import type { paths } from './generated/schema';
import type { BusinessSummary } from './platform';
import { toResult, type ApiResult } from './result';

export interface BusinessesApi {
  get(businessId: string): Promise<ApiResult<BusinessSummary>>;
}

export function createBusinessesApi(client: Client<paths>): BusinessesApi {
  return {
    async get(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}',
          { params: { path: { business_id: businessId } } },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
