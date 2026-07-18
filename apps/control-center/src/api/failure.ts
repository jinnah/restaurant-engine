import type { ApiResult, ErrorEnvelope } from '@restaurant-engine/api-client';

/**
 * A failed facade result promoted to a throwable for mutation flows. The
 * message is the backend's own envelope message (already neutral by
 * contract) or a generic fallback — never request payload content.
 */
export class ApiFailure extends Error {
  constructor(
    readonly status: number | null,
    readonly envelope: ErrorEnvelope | null,
  ) {
    super(envelope?.error.message ?? 'The request could not be completed.');
    this.name = 'ApiFailure';
  }
}

/** Unwrap an ApiResult, throwing ApiFailure on the error branch. */
export function unwrap<T>(result: ApiResult<T>): T {
  if (!result.ok) {
    throw new ApiFailure(result.status, result.envelope);
  }
  return result.data;
}

/** Narrow an unknown thrown value to ApiFailure (mutations throw only these). */
export function asApiFailure(error: unknown): ApiFailure {
  return error instanceof ApiFailure ? error : new ApiFailure(null, null);
}
