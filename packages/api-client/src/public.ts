// Public storefront facade (M2C site; M3D menu).
//
// The Business is resolved server-side from the request's destination Host
// (same-origin with the tenant subdomain). These methods take NO business,
// slug, Host, or tenant argument and send no tenant-selection header, query
// parameter, body, or cookie of their own — a caller cannot select a tenant.
// The facade does not resolve tenancy. Unused by the storefront until M4.
//
// There is deliberately no media URL builder: every image URL a consumer
// needs already arrives inside the menu payload, relative and same-origin.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type PublicSiteSummary = components['schemas']['PublicSiteSummary'];
export type PublicMenu = components['schemas']['PublicMenu'];
export type PublicMenuCategory = components['schemas']['PublicMenuCategory'];
export type PublicMenuItem = components['schemas']['PublicMenuItem'];
export type PublicMenuImage = components['schemas']['PublicMenuImage'];
export type PublicMenuImageVariant =
  components['schemas']['PublicMenuImageVariant'];
export type PublicModifierGroup = components['schemas']['PublicModifierGroup'];
export type PublicModifierOption =
  components['schemas']['PublicModifierOption'];

export interface PublicApi {
  getSite(): Promise<ApiResult<PublicSiteSummary>>;
  /** The public menu of the Host-resolved Business (no tenant argument). */
  getMenu(): Promise<ApiResult<PublicMenu>>;
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

    async getMenu() {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/public/menu',
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
