import type { QueryClient } from '@tanstack/react-query';
import type { ApiResult } from '@restaurant-engine/api-client';
import { unwrap } from '../api/failure';
import { clearAuthenticatedState } from '../auth/session';

/**
 * Unwrap a privileged platform result. A 401 means the session died
 * server-side (revocation, expiry): every trace of authenticated state
 * is cleared before the failure propagates — RequireAuth then routes to
 * login (ADR-015 decision 4 applied to the first privileged queries).
 * All other failures throw ApiFailure for the caller's error mapping.
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
