import type { QueryClient } from '@tanstack/react-query';
import type { ApiResult } from '@restaurant-engine/api-client';
import { currentCsrfToken } from '../auth/csrf';
import { clearAuthenticatedState, SESSION_KEY } from '../auth/session';
import { ApiFailure, unwrap } from './failure';

/**
 * The CSRF token for an unsafe request, read from the session cache at call
 * time (ADR-015 decision 4) so a rotated session always supplies the fresh
 * value. A missing token means the session is gone; treating it as a 401
 * routes through the same clearing path a server 401 would.
 */
export function requireCsrf(queryClient: QueryClient): string {
  const token = currentCsrfToken(queryClient);
  if (token === null) {
    throw new ApiFailure(401, null);
  }
  return token;
}

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
  if (!result.ok && result.status === 403) {
    // The session is still valid, but this actor may no longer hold the
    // capability — a role change mid-session is the usual cause. Revalidate
    // the session so `memberships[].role` becomes authoritative again and the
    // affordances recompute from it rather than from a stale snapshot.
    // ADR-015 names invalidateQueries as an explicit revalidation trigger, so
    // this does not fight the staleTime: Infinity policy.
    await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
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
