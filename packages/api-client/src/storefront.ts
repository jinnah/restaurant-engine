// Storefront administration facade (M4B-M4C, ADR-020).
//
// Business-scoped operations: the overview (the draft's only full
// administrative read, where `draft: null` is the valid first-use
// absence), the render-equivalent draft preview (M4C — the same public
// projection contract the storefront renderer consumes, with
// authenticated media URLs), the create-or-update draft PUT with its
// explicit intent representation (omitted/null expected_lock_version =
// create, an integer = update), publication and restore (owner-only;
// both carry the draft's expected lock version, and a stale write is a
// 409 whose envelope details carry the current value), and the history
// list/detail (published + archived rows only — never the draft). The
// platform design command lives on the platform facade group.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type StorefrontConfig = components['schemas']['StorefrontConfig'];
export type StorefrontOverview = components['schemas']['StorefrontOverview'];
export type DraftView = components['schemas']['DraftView'];
export type DraftPut = components['schemas']['DraftPut'];
export type PublishRequest = components['schemas']['PublishRequest'];
export type RestoreRequest = components['schemas']['RestoreRequest'];
export type VersionSummary = components['schemas']['VersionSummary'];
export type VersionPage = components['schemas']['VersionPage'];
export type VersionDetail = components['schemas']['VersionDetail'];
export type DesignVariant = components['schemas']['DesignVariant'];
export type PublicStorefront = components['schemas']['PublicStorefront'];

const CSRF_HEADER = 'X-CSRF-Token';

export interface StorefrontApi {
  /** The overview: current draft (or null) plus the published summary. */
  get(businessId: string): Promise<ApiResult<StorefrontOverview>>;
  /**
   * The render-equivalent projection of the current draft (M4C): enabled
   * sections only, authenticated media URLs, never cached. 404 when no
   * draft exists.
   */
  preview(businessId: string): Promise<ApiResult<PublicStorefront>>;
  /** Create or replace the draft (full document, explicit intent). */
  putDraft(
    businessId: string,
    body: DraftPut,
    csrfToken: string,
  ): Promise<ApiResult<DraftView>>;
  /** Publish the draft (owner only); requires its exact lock version. */
  publish(
    businessId: string,
    body: PublishRequest,
    csrfToken: string,
  ): Promise<ApiResult<StorefrontOverview>>;
  /** History page: published + archived versions, newest first. */
  listVersions(
    businessId: string,
    params?: { limit?: number; offset?: number },
  ): Promise<ApiResult<VersionPage>>;
  /** One history row with its composition (never the draft). */
  getVersion(
    businessId: string,
    versionId: string,
  ): Promise<ApiResult<VersionDetail>>;
  /**
   * Restore an archived version into the draft (owner only). Overwrites
   * the current draft in place and returns the updated draft.
   */
  restoreVersion(
    businessId: string,
    versionId: string,
    body: RestoreRequest,
    csrfToken: string,
  ): Promise<ApiResult<DraftView>>;
}

export function createStorefrontApi(client: Client<paths>): StorefrontApi {
  const csrf = (csrfToken: string) => ({ [CSRF_HEADER]: csrfToken });
  const path = (businessId: string) => ({
    params: { path: { business_id: businessId } },
  });
  const versionPath = (businessId: string, versionId: string) => ({
    params: { path: { business_id: businessId, version_id: versionId } },
  });

  return {
    async get(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/storefront',
          path(businessId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async preview(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/storefront/preview',
          path(businessId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async putDraft(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.PUT(
          '/api/v1/businesses/{business_id}/storefront/draft',
          { ...path(businessId), body, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async publish(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/storefront/publish',
          { ...path(businessId), body, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async listVersions(businessId, params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/storefront/versions',
          {
            params: {
              path: { business_id: businessId },
              query: { limit: params?.limit, offset: params?.offset },
            },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getVersion(businessId, versionId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/storefront/versions/{version_id}',
          versionPath(businessId, versionId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async restoreVersion(businessId, versionId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/storefront/versions/{version_id}/restore',
          {
            ...versionPath(businessId, versionId),
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
