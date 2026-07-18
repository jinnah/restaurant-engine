import type { QueryClient } from '@tanstack/react-query';
import type { ApiClient, SessionView } from '@restaurant-engine/api-client';

// TanStack Query is the ONLY session store (ADR-015). The cache holds
// exactly two value shapes; unexpected bootstrap failures stay query
// errors and are never cached as session values.
export type SessionState =
  | { kind: 'authenticated'; session: SessionView; csrfToken: string }
  | { kind: 'anonymous' };

export const SESSION_KEY = ['session'] as const;

/** Unexpected bootstrap failure — anything other than the expected 401. */
export class SessionBootstrapError extends Error {
  constructor() {
    super('The session could not be loaded.');
    this.name = 'SessionBootstrapError';
  }
}

/**
 * Resolve the authoritative session state from `GET /auth/session`.
 *
 * The expected 401 is a *value* (anonymous), not an error, so React
 * Query's error state is reserved for genuinely unexpected failures.
 */
export async function fetchSessionState(
  client: ApiClient,
): Promise<SessionState> {
  const result = await client.auth.getSession();
  if (result.ok) {
    return {
      kind: 'authenticated',
      session: result.data,
      csrfToken: result.data.csrf_token,
    };
  }
  if (result.status === 401) {
    return { kind: 'anonymous' };
  }
  throw new SessionBootstrapError();
}

export function sessionQueryOptions(client: ApiClient) {
  return {
    queryKey: SESSION_KEY,
    queryFn: () => fetchSessionState(client),
  };
}

/**
 * Authoritative session establishment (ADR-015): fetch the enriched
 * session view and populate the cache only from it. Used after login and
 * after existing-user invitation acceptance — the login response is
 * never cast or cached as the session. Throws on any failure, including
 * an unexpected post-login 401.
 */
export async function establishSession(
  client: ApiClient,
  queryClient: QueryClient,
): Promise<SessionState> {
  const state = await fetchSessionState(client);
  if (state.kind !== 'authenticated') {
    throw new SessionBootstrapError();
  }
  queryClient.setQueryData<SessionState>(SESSION_KEY, state);
  return state;
}

/**
 * Drop every trace of an authenticated user: cancel in-flight queries,
 * set the session to anonymous immediately (a *set*, not an invalidate —
 * no refetch loop against a known-expired session), and remove all other
 * cached data. Used on logout, privileged-request 401, and password-reset
 * success (the backend revoked every session).
 */
export async function clearAuthenticatedState(
  queryClient: QueryClient,
): Promise<void> {
  await queryClient.cancelQueries();
  queryClient.setQueryData<SessionState>(SESSION_KEY, { kind: 'anonymous' });
  queryClient.removeQueries({
    predicate: (query) => query.queryKey[0] !== SESSION_KEY[0],
  });
}
