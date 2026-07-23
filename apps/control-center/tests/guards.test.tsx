import { screen, waitFor } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import {
  adminSessionView,
  apiError,
  makeClient,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

test('loading flashes neither protected nor guest-only content', () => {
  const pendingForever = new Promise<never>(() => {
    /* never resolves */
  });
  const client = makeClient({
    auth: { getSession: vi.fn(() => pendingForever) },
  });

  const protectedRender = renderApp('/', client);
  expect(screen.getByRole('status')).toHaveTextContent(
    /checking your session/i,
  );
  expect(
    screen.queryByRole('heading', { name: /restaurant dashboard/i }),
  ).toBeNull();
  protectedRender.view.unmount();

  renderApp('/login', client);
  expect(screen.getByRole('status')).toHaveTextContent(
    /checking your session/i,
  );
  expect(screen.queryByLabelText(/email/i)).toBeNull();
});

test('an anonymous visitor to a protected route is redirected to login', async () => {
  const { router } = renderApp('/', makeClient());
  expect(
    await screen.findByRole('heading', { name: /^sign in$/i }),
  ).toBeInTheDocument();
  expect(router.state.location.pathname).toBe('/login');
  expect(router.state.location.search).toBe('');
});

test('the intended internal path is preserved in next', async () => {
  const { router } = renderApp('/?tab=activity', makeClient());
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
  expect(router.state.location.search).toBe(
    '?next=' + encodeURIComponent('/?tab=activity'),
  );
});

test('an unexpected bootstrap failure is retryable, not anonymous', async () => {
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(apiError(503, null))
    .mockResolvedValue(ok(sessionView()));
  const { router } = renderApp('/', makeClient({ auth: { getSession } }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/could not check your session/i);
  // Not redirected to login: this is an error, not anonymous state.
  expect(router.state.location.pathname).toBe('/');

  fireEvent.click(screen.getByRole('button', { name: /try again/i }));
  expect(
    await screen.findByRole('heading', { name: /restaurant dashboard/i }),
  ).toBeInTheDocument();
});

test('an authenticated visitor to /login is sent to the memberships landing', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
  });
  const { router } = renderApp('/login', client);
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/');
  });
});

test('an authenticated visitor with a safe next lands on that path', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
  });
  const { router } = renderApp(
    '/login?next=' + encodeURIComponent('/somewhere?page=2'),
    client,
  );
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/somewhere');
  });
  expect(router.state.location.search).toBe('?page=2');
});

test('an already-authenticated admin at /login with an unreachable owner next goes to the platform home', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
  });
  const { router } = renderApp(
    '/login?next=' +
      encodeURIComponent(
        '/businesses/99999999-9999-4999-8999-999999999999/menu',
      ),
    client,
  );
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/platform');
  });
});

test('an already-authenticated owner at /login with a platform next goes to their dashboard', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
  });
  const { router } = renderApp(
    '/login?next=' + encodeURIComponent('/platform/businesses'),
    client,
  );
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/');
  });
});

test.each([
  ['cross-origin', 'https://evil.example/x'],
  ['scheme-relative', '//evil.example'],
  ['login loop', '/login'],
  ['token-bearing', '/x?invite_token=abc'],
])(
  'an authenticated visitor with an unsafe next (%s) falls back to /',
  async (_name, next) => {
    const client = makeClient({
      auth: { getSession: vi.fn(async () => ok(sessionView())) },
    });
    const { router } = renderApp(
      '/login?next=' + encodeURIComponent(next),
      client,
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  },
);
