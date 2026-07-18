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
 * An establishment attempt that lost its authority mid-flight: either
 * authenticated state was cleared (logout, password-reset success,
 * privileged 401) or a newer establishment attempt started. Its response
 * must never reach the cache. Rendered like any other retryable
 * establishment failure — the generation is an internal detail.
 */
export class StaleSessionEstablishmentError extends Error {
  constructor() {
    super('The session could not be loaded.');
    this.name = 'StaleSessionEstablishmentError';
  }
}

// Session-establishment generation (ADR-015): the guard that makes stale
// *direct* responses unable to touch the cache. cancelQueries protects
// query-driven fetches, but establishSession awaits its own request, so a
// response that started before clearAuthenticatedState — or before a
// newer establishment attempt — could otherwise resolve afterwards and
// overwrite the newer truth. Every clear and every establishment attempt
// advances the generation; an attempt may commit only if the generation
// still equals the one it captured at start.
let sessionGeneration = 0;

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
    // Session revalidation is always explicit (login establishment,
    // logout, a user-triggered retry, or invalidateQueries) — a cached
    // value must never be refetched merely because a guard remounted.
    // In particular, after clearAuthenticatedState sets `anonymous`, an
    // automatic mount refetch would race the redirect and could loop
    // (the binding M2E ruling forbids exactly that).
    staleTime: Infinity,
  };
}

/**
 * Authoritative session establishment (ADR-015): fetch the enriched
 * session view and populate the cache only from it. Used after login and
 * after existing-user invitation acceptance — the login response is
 * never cast or cached as the session. Throws on any failure, including
 * an unexpected post-login 401. Each attempt claims the newest
 * generation at start and commits only if it is still the newest when
 * its response arrives — a stale attempt (superseded by a clear or by a
 * later attempt) throws instead of writing, and never disturbs whatever
 * newer state the cache holds.
 */
export async function establishSession(
  client: ApiClient,
  queryClient: QueryClient,
): Promise<SessionState> {
  sessionGeneration += 1;
  const generation = sessionGeneration;
  const state = await fetchSessionState(client);
  if (generation !== sessionGeneration) {
    throw new StaleSessionEstablishmentError();
  }
  if (state.kind !== 'authenticated') {
    throw new SessionBootstrapError();
  }
  queryClient.setQueryData<SessionState>(SESSION_KEY, state);
  return state;
}

/**
 * Drop every trace of an authenticated user: advance the establishment
 * generation (so any in-flight establishSession response is stale and
 * cannot write), cancel in-flight queries, set the session to anonymous
 * immediately (a *set*, not an invalidate — no refetch loop against a
 * known-expired session), and remove all other cached data. Used on
 * logout, privileged-request 401, and password-reset success (the
 * backend revoked every session).
 */
export async function clearAuthenticatedState(
  queryClient: QueryClient,
): Promise<void> {
  sessionGeneration += 1;
  await queryClient.cancelQueries();
  queryClient.setQueryData<SessionState>(SESSION_KEY, { kind: 'anonymous' });
  queryClient.removeQueries({
    predicate: (query) => query.queryKey[0] !== SESSION_KEY[0],
  });
}
