// Shared result shape for every facade method.

import { isErrorEnvelope, type ErrorEnvelope } from './errors';

/**
 * Result of an API call. `ok: false` with a null `status` means the request
 * never produced a usable HTTP response (network failure or an unparseable
 * body); a null `envelope` means the failure carried no ADR-008 envelope.
 */
export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number | null; envelope: ErrorEnvelope | null };

export function toResult<T>(
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
