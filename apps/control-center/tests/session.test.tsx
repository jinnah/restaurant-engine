import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { vi, expect, test } from 'vitest';
import type { ReactNode } from 'react';
import type { ApiClient } from '@restaurant-engine/api-client';
import { ClientProvider } from '../src/api/ClientProvider';
import { createQueryClient } from '../src/api/queryClient';
import { useSession } from '../src/auth/useSession';
import { apiError, makeClient, ok, sessionView } from './support/mockClient';

function renderSession(client: ApiClient) {
  const queryClient = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ClientProvider client={client}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ClientProvider>
  );
  return renderHook(() => useSession(), { wrapper });
}

test('the expected 401 resolves to anonymous, not an error', async () => {
  const { result } = renderSession(makeClient());
  expect(result.current.status).toBe('loading');
  await waitFor(() => {
    expect(result.current.status).toBe('anonymous');
  });
});

test('a session response resolves to authenticated with the CSRF token', async () => {
  const view = sessionView();
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(view)) },
  });
  const { result } = renderSession(client);
  await waitFor(() => {
    expect(result.current.status).toBe('authenticated');
  });
  if (result.current.status !== 'authenticated') throw new Error('unreachable');
  expect(result.current.session).toEqual(view);
  expect(result.current.csrfToken).toBe('csrf-token-1');
});

test('an unexpected bootstrap failure is a distinct, retryable error', async () => {
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(apiError(503, null))
    .mockResolvedValue(ok(sessionView()));
  const client = makeClient({ auth: { getSession } });
  const { result } = renderSession(client);

  await waitFor(() => {
    expect(result.current.status).toBe('error');
  });
  if (result.current.status !== 'error') throw new Error('unreachable');
  result.current.retry();
  await waitFor(() => {
    expect(result.current.status).toBe('authenticated');
  });
  // The retry refetched the session only — nothing else was called.
  expect(getSession).toHaveBeenCalledTimes(2);
});

test('a network-level failure (null status) is also an error, never anonymous', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => apiError(null, null)) },
  });
  const { result } = renderSession(client);
  await waitFor(() => {
    expect(result.current.status).toBe('error');
  });
});
