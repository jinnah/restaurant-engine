// Public storefront facade (M2C).
//
// The Business is resolved server-side from the request's destination Host
// (same-origin with the tenant subdomain). `getSite` takes NO business, slug,
// Host, or tenant argument and sends no tenant-selection header, query
// parameter, body, or cookie of its own — a caller cannot select a tenant.
// The facade does not resolve tenancy. Unused by the storefront until M4.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type PublicSiteSummary = components['schemas']['PublicSiteSummary'];

export interface PublicApi {
  getSite(): Promise<ApiResult<PublicSiteSummary>>;
}

export function createPublicApi(client: Client<paths>): PublicApi {
  return {
    async getSite() {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/public/site',
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
