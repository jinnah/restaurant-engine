// Platform business-management facade (M2B).
//
// Every unsafe call sends credentials (the session cookie) via the internal
// client; the CSRF synchronizer token must be passed back explicitly on
// unsafe calls (ADR-010). Lifecycle commands take no data but send an empty
// body so the strict server schema accepts them.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

type GeneratedBusinessCreate = components['schemas']['BusinessCreate'];
export type BusinessSummary = components['schemas']['BusinessSummary'];
export type BusinessPage = components['schemas']['BusinessPage'];

/**
 * Fields the backend supplies server-side defaults for. The OpenAPI
 * contract lists only `name`/`slug` as required; openapi-typescript still
 * marks default-valued fields required in the generated type (its
 * `defaultNonNullable` idiom), so the facade widens exactly these fields
 * back to optional. Extend this union ONLY when the backend adds another
 * server-defaulted create field.
 */
type ServerDefaultedCreateField = 'timezone' | 'currency';

/**
 * Create-business input, derived from the generated contract (review
 * finding L-3): a new required backend field flows through `Omit` and
 * every call site fails to compile; if a recognized defaulted field is
 * removed or renamed, `Pick` itself fails to compile. Only `timezone` and
 * `currency` are widened to optional — the server fills them.
 */
export type BusinessCreate = Omit<
  GeneratedBusinessCreate,
  ServerDefaultedCreateField
> &
  Partial<Pick<GeneratedBusinessCreate, ServerDefaultedCreateField>>;

const CSRF_HEADER = 'X-CSRF-Token';

export interface PlatformApi {
  createBusiness(
    body: BusinessCreate,
    csrfToken: string,
  ): Promise<ApiResult<BusinessSummary>>;
  listBusinesses(params?: {
    limit?: number;
    offset?: number;
  }): Promise<ApiResult<BusinessPage>>;
  getBusiness(businessId: string): Promise<ApiResult<BusinessSummary>>;
  activate(
    businessId: string,
    csrfToken: string,
  ): Promise<ApiResult<BusinessSummary>>;
  suspend(
    businessId: string,
    csrfToken: string,
  ): Promise<ApiResult<BusinessSummary>>;
  reactivate(
    businessId: string,
    csrfToken: string,
  ): Promise<ApiResult<BusinessSummary>>;
  close(
    businessId: string,
    csrfToken: string,
  ): Promise<ApiResult<BusinessSummary>>;
}

export function createPlatformApi(client: Client<paths>): PlatformApi {
  const csrf = (csrfToken: string) => ({ [CSRF_HEADER]: csrfToken });
  const path = (businessId: string) => ({
    params: { path: { business_id: businessId } },
  });

  return {
    async createBusiness(body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/businesses',
          // Narrow transport cast, still required: openapi-fetch demands
          // the exact generated body type, whose defaulted fields are
          // non-optional. BusinessCreate differs from it ONLY in the
          // optionality of the two ServerDefaultedCreateField members, so
          // the cast cannot mask a missing new field.
          { body: body as GeneratedBusinessCreate, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async listBusinesses(params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/platform/businesses',
          {
            params: { query: { limit: params?.limit, offset: params?.offset } },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getBusiness(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/platform/businesses/{business_id}',
          path(businessId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async activate(businessId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/businesses/{business_id}/activate',
          { ...path(businessId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async suspend(businessId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/businesses/{business_id}/suspend',
          { ...path(businessId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async reactivate(businessId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/businesses/{business_id}/reactivate',
          { ...path(businessId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async close(businessId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/platform/businesses/{business_id}/close',
          { ...path(businessId), body: {}, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
