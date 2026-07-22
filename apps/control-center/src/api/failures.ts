import type { QueryClient } from '@tanstack/react-query';
import type { ApiResult } from '@restaurant-engine/api-client';
import { clearAuthenticatedState } from '../auth/session';
import { unwrap, type ApiFailure } from './failure';

/**
 * Unwrap a privileged result. A 401 means the session died server-side
 * (revocation, expiry): every trace of authenticated state is cleared before
 * the failure propagates — RequireAuth then routes to login (ADR-015
 * decision 4). All other failures throw ApiFailure for the caller to map.
 *
 * Moved here from the platform feature in M3E: it was never platform-
 * specific, and the business workspace needs the identical behaviour.
 */
export async function unwrapPrivileged<T>(
  queryClient: QueryClient,
  result: ApiResult<T>,
): Promise<T> {
  if (!result.ok && result.status === 401) {
    await clearAuthenticatedState(queryClient);
  }
  return unwrap(result);
}

/**
 * What a failure means for presentation. Deliberately derived from the HTTP
 * status alone: the backend's neutral 404 covers "does not exist", "not
 * yours", and "you are not a member" on purpose, and the UI must not try to
 * tell them apart or it would leak exactly what the contract hides.
 */
export type FailureKind =
  | 'auth' // 401 — session gone; RequireAuth takes over
  | 'denied' // 403 — authenticated, capability missing
  | 'gone' // 404 — absent, foreign, or inaccessible. Never distinguished.
  | 'conflict' // 409 — a rule or a concurrent change refused this
  | 'invalid' // 422 — the payload failed validation
  | 'tooLarge' // 413 — over the deployment's upload cap
  | 'offline' // no status at all: the request never completed
  | 'other';

export function classifyFailure(failure: ApiFailure): FailureKind {
  switch (failure.status) {
    case 401:
      return 'auth';
    case 403:
      return 'denied';
    case 404:
      return 'gone';
    case 409:
      return 'conflict';
    case 413:
      return 'tooLarge';
    case 422:
      return 'invalid';
    case null:
      return 'offline';
    default:
      return 'other';
  }
}

/**
 * The governed limit a 409 carried, when it carried one.
 *
 * `details` is an open object in the envelope contract, so the value is
 * narrowed rather than trusted: a missing, non-numeric, or non-integer
 * `limit` yields null and the caller falls back to its generic message.
 */
export function conflictLimit(failure: ApiFailure): number | null {
  const details = failure.envelope?.error.details;
  if (details === null || details === undefined) {
    return null;
  }
  const limit = (details as Record<string, unknown>)['limit'];
  return typeof limit === 'number' && Number.isInteger(limit) && limit >= 0
    ? limit
    : null;
}
