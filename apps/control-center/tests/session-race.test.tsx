// Regression coverage for the session-establishment generation guard
// (ADR-015): a direct establishment response that became stale — because
// authenticated state was cleared or because a newer establishment
// attempt started — must never write to the canonical ['session'] cache.
// All timing is controlled through deferred promises; no sleeps.

import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import type {
  ApiResult,
  InvitationAcceptedResponse,
  InvitationPreviewResponse,
  SessionView,
} from '@restaurant-engine/api-client';
import { createQueryClient } from '../src/api/queryClient';
import {
  SESSION_KEY,
  StaleSessionEstablishmentError,
  clearAuthenticatedState,
  establishSession,
} from '../src/auth/session';
import {
  apiError,
  makeClient,
  membership,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** Deterministically drain the microtask continuations of a resolved
 * establishment attempt (each `await` in the chain is one hop). */
async function flushMicrotasks(hops = 10) {
  for (let i = 0; i < hops; i += 1) {
    await Promise.resolve();
  }
}

test('an establishment resolving after clearAuthenticatedState cannot restore authenticated state', async () => {
  const queryClient = createQueryClient();
  const response = deferred<ApiResult<SessionView>>();
  const client = makeClient({
    auth: { getSession: vi.fn(() => response.promise) },
  });

  // 1. Establishment starts and remains in flight.
  const attempt = establishSession(client, queryClient);

  // 2. Authenticated state is cleared (logout/reset/privileged 401 path).
  await clearAuthenticatedState(queryClient);
  expect(queryClient.getQueryData(SESSION_KEY)).toEqual({ kind: 'anonymous' });

  // 3. The old request then resolves with an authenticated SessionView.
  response.resolve(ok(sessionView()));

  // 4. The attempt is rejected as stale and the cache stays anonymous.
  await expect(attempt).rejects.toBeInstanceOf(StaleSessionEstablishmentError);
  expect(queryClient.getQueryData(SESSION_KEY)).toEqual({ kind: 'anonymous' });
});

test('an older establishment cannot overwrite a newer one', async () => {
  const queryClient = createQueryClient();
  const first = deferred<ApiResult<SessionView>>();
  const second = deferred<ApiResult<SessionView>>();
  const getSession = vi
    .fn<() => Promise<ApiResult<SessionView>>>()
    .mockImplementationOnce(() => first.promise)
    .mockImplementationOnce(() => second.promise);
  const client = makeClient({ auth: { getSession } });

  const newerView = sessionView({ csrf_token: 'csrf-newer' });

  // A starts, then B starts: B is now the only attempt allowed to commit.
  const attemptA = establishSession(client, queryClient);
  const attemptB = establishSession(client, queryClient);

  // B resolves and establishes the newer authoritative session.
  second.resolve(ok(newerView));
  await expect(attemptB).resolves.toMatchObject({ kind: 'authenticated' });
  expect(queryClient.getQueryData(SESSION_KEY)).toEqual({
    kind: 'authenticated',
    session: newerView,
    csrfToken: 'csrf-newer',
  });

  // A resolves later with older data: rejected, and B's result survives.
  first.resolve(ok(sessionView({ csrf_token: 'csrf-older' })));
  await expect(attemptA).rejects.toBeInstanceOf(StaleSessionEstablishmentError);
  expect(queryClient.getQueryData(SESSION_KEY)).toEqual({
    kind: 'authenticated',
    session: newerView,
    csrfToken: 'csrf-newer',
  });
});

test('a stale response that is the expected 401 also stays silent', async () => {
  // Stale-ness is decided before the response shape is interpreted: a
  // stale anonymous response must not masquerade as a bootstrap error or
  // write anything either.
  const queryClient = createQueryClient();
  const response = deferred<ApiResult<SessionView>>();
  const client = makeClient({
    auth: { getSession: vi.fn(() => response.promise) },
  });

  const attempt = establishSession(client, queryClient);
  await clearAuthenticatedState(queryClient);
  response.resolve(apiError(401, null));
  await expect(attempt).rejects.toBeInstanceOf(StaleSessionEstablishmentError);
  expect(queryClient.getQueryData(SESSION_KEY)).toEqual({ kind: 'anonymous' });
});

test('signing out while an invitation-recovery session refresh is in flight stays signed out', async () => {
  // The concrete reachable overlap from the review: membershipMissing
  // offers both "Refresh session" and "Sign out". The refresh response
  // that started before logout must not restore authenticated UI.
  const preview: InvitationPreviewResponse = {
    business_name: 'Juniper',
    role: 'staff',
    email_hint: 'o***@example.com',
  };
  const accepted: InvitationAcceptedResponse = {
    status: 'accepted',
    business_id: '7a1c2d3e-0f00-4b1a-8c2d-3e4f5a6b7c8d',
    email: 'owner@example.com',
    role: 'staff',
  };
  const refreshedView = sessionView({
    memberships: [
      membership(),
      membership({
        business_id: accepted.business_id,
        business_name: 'Juniper',
      }),
    ],
  });

  const staleRefresh = deferred<ApiResult<SessionView>>();
  const getSession = vi
    .fn<() => Promise<ApiResult<SessionView>>>()
    .mockResolvedValueOnce(ok(sessionView())) // bootstrap: authenticated
    .mockResolvedValueOnce(ok(sessionView())) // post-accept refresh: membership missing
    .mockImplementationOnce(() => staleRefresh.promise); // user-triggered refresh
  const logout = vi.fn(async () => ok({ status: 'logged_out' as const }));
  const client = makeClient({
    auth: { getSession, logout },
    invitations: {
      preview: vi.fn(async () => ok(preview)),
      acceptExisting: vi.fn(async () => ok(accepted)),
    },
  });
  const { queryClient } = renderApp('/invitations/accept', client);

  // Reach membershipMissing: paste token, confirm, accept, refresh lacks it.
  fireEvent.change(await screen.findByLabelText(/invitation token/i), {
    target: { value: 'raw-token' },
  });
  fireEvent.click(screen.getByRole('button', { name: /continue/i }));
  fireEvent.click(
    await screen.findByRole('button', { name: /accept invitation/i }),
  );
  await screen.findByText(/has not appeared in your session yet/i);

  // Start the recovery refresh; it stays in flight.
  fireEvent.click(screen.getByRole('button', { name: /refresh session/i }));

  // Sign out while the refresh is pending.
  fireEvent.click(screen.getByRole('button', { name: /sign out/i }));
  await waitFor(() => {
    expect(queryClient.getQueryData(SESSION_KEY)).toEqual({
      kind: 'anonymous',
    });
  });
  expect(await screen.findByText(/paste the invitation token/i)).toBeVisible();

  // The pre-logout refresh now resolves authenticated — and changes nothing.
  staleRefresh.resolve(ok(refreshedView));
  await flushMicrotasks();
  expect(queryClient.getQueryData(SESSION_KEY)).toEqual({ kind: 'anonymous' });
  expect(screen.queryByText(/signed in as/i)).toBeNull();
  expect(getSession).toHaveBeenCalledTimes(3);
});
