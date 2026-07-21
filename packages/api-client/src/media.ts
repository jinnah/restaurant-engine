// Media administration facade (M3C, ADR-017).
//
// Business-scoped image management. List/get/delete use the typed
// openapi-fetch client; upload hand-builds a multipart FormData request
// because the endpoint declares no typed request body (the binding
// upload correction — the server owns the byte stream). `fileUrl` builds
// the opaque admin-preview URL from the asset id and a logical variant
// name — a plain `<img src>` needs a URL, not a fetch. Internal storage
// keys never appear anywhere here.

import type { Client } from 'openapi-fetch';

import type { ApiClientOptions } from './client';
import type { components, paths } from './generated/schema';
import { isErrorEnvelope } from './errors';
import { toResult, type ApiResult } from './result';

export type MediaAssetView = components['schemas']['MediaAssetView'];
export type MediaAssetPage = components['schemas']['MediaAssetPage'];
export type MediaVariantView = components['schemas']['MediaVariantView'];
export type MediaDeletedResponse =
  components['schemas']['MediaDeletedResponse'];

export type MediaVariant = 'canonical' | 'w320' | 'w640' | 'w1280';

const CSRF_HEADER = 'X-CSRF-Token';

export interface MediaListParams {
  limit?: number;
  offset?: number;
  status?: 'pending' | 'active';
}

export interface MediaApi {
  /** Upload one static JPEG/PNG/WebP image (multipart); returns the asset. */
  uploadAsset(
    businessId: string,
    file: Blob,
    filename: string,
    csrfToken: string,
  ): Promise<ApiResult<MediaAssetView>>;
  listAssets(
    businessId: string,
    params?: MediaListParams,
  ): Promise<ApiResult<MediaAssetPage>>;
  getAsset(
    businessId: string,
    assetId: string,
  ): Promise<ApiResult<MediaAssetView>>;
  deleteAsset(
    businessId: string,
    assetId: string,
    csrfToken: string,
  ): Promise<ApiResult<MediaDeletedResponse>>;
  /** The authorized admin-preview URL for one stored object (no fetch). */
  fileUrl(businessId: string, assetId: string, variant: MediaVariant): string;
}

export function createMediaApi(
  client: Client<paths>,
  options: ApiClientOptions,
): MediaApi {
  const csrf = (csrfToken: string) => ({ [CSRF_HEADER]: csrfToken });
  const doFetch = options.fetch ?? fetch;
  const base = options.baseUrl.replace(/\/$/, '');

  return {
    async uploadAsset(businessId, file, filename, csrfToken) {
      try {
        const form = new FormData();
        form.append('file', file, filename);
        // openapi-fetch's fetch takes a single Request; build one so the
        // multipart upload uses the same injectable transport as the rest.
        const request = new Request(
          `${base}/api/v1/businesses/${businessId}/media`,
          {
            method: 'POST',
            body: form,
            headers: csrf(csrfToken),
            credentials: 'include',
          },
        );
        const response = await doFetch(request);
        const body: unknown = await response.json().catch(() => undefined);
        if (response.ok) {
          return {
            ok: true,
            status: response.status,
            data: body as MediaAssetView,
          };
        }
        return {
          ok: false,
          status: response.status,
          envelope: isErrorEnvelope(body) ? body : null,
        };
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async listAssets(businessId, params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/media',
          {
            params: {
              path: { business_id: businessId },
              query: {
                limit: params?.limit,
                offset: params?.offset,
                status: params?.status,
              },
            },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getAsset(businessId, assetId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/media/{asset_id}',
          {
            params: { path: { business_id: businessId, asset_id: assetId } },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async deleteAsset(businessId, assetId, csrfToken) {
      try {
        const { data, error, response } = await client.DELETE(
          '/api/v1/businesses/{business_id}/media/{asset_id}',
          {
            params: { path: { business_id: businessId, asset_id: assetId } },
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    fileUrl(businessId, assetId, variant) {
      return `${base}/api/v1/businesses/${businessId}/media/${assetId}/file/${variant}`;
    },
  };
}
