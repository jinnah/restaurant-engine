// Handwritten facade over the generated contract (ADR-004/ADR-009).
//
// Applications call intent-named methods and receive a discriminated
// result — success payload or the typed ADR-008 error envelope — so
// callers get exhaustive narrowing and never see generator idioms.

import { createInternalClient, type ApiClientOptions } from './client';
import { isErrorEnvelope, type ErrorEnvelope } from './errors';
import type { components } from './generated/schema';

export type LivenessResponse = components['schemas']['LivenessResponse'];
export type ReadinessResponse = components['schemas']['ReadinessResponse'];

/**
 * Result of an API call. `ok: false` with a null `status` means the request
 * never produced a usable HTTP response (network failure or an unparseable
 * body); a null `envelope` means the failure carried no ADR-008 envelope.
 */
export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number | null; envelope: ErrorEnvelope | null };

export interface ApiClient {
  getLiveness(): Promise<ApiResult<LivenessResponse>>;
  getReadiness(): Promise<ApiResult<ReadinessResponse>>;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const client = createInternalClient(options);

  return {
    async getLiveness(): Promise<ApiResult<LivenessResponse>> {
      try {
        const { data, error, response } = await client.GET('/health/live');
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getReadiness(): Promise<ApiResult<ReadinessResponse>> {
      try {
        const { data, error, response } = await client.GET('/health/ready');
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}

function toResult<T>(
  data: T | undefined,
  error: unknown,
  response: Response,
): ApiResult<T> {
  if (data !== undefined) {
    return { ok: true, status: response.status, data };
  }
  return {
    ok: false,
    status: response.status,
    envelope: isErrorEnvelope(error) ? error : null,
  };
}
