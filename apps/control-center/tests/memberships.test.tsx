import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import {
  apiError,
  envelope,
  makeClient,
  membership,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

function authenticatedClient(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    ...overrides,
    auth: {
      getSession: vi.fn(async () => ok(sessionView())),
      ...overrides.auth,
    },
  });
}

test('the landing shows identity and session-provided memberships only', async () => {
  const view = sessionView({
    memberships: [
      membership(),
      membership({
        business_id: '7a1c2d3e-0f00-4b1a-8c2d-3e4f5a6b7c8d',
        business_slug: 'juniper',
        business_name: 'Juniper',
        role: 'staff',
        business_status: 'suspended',
      }),
    ],
  });
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(view)) },
  });
  renderApp('/', client);

  expect(
    await screen.findByRole('heading', { name: /restaurant dashboard/i }),
  ).toBeInTheDocument();
  expect(screen.getByText(/signed in as/i)).toHaveTextContent('Test Owner');
  expect(screen.getByText('(owner@example.com)')).toBeInTheDocument();

  const items = screen.getAllByRole('listitem');
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent('Shalik');
  expect(items[0]).toHaveTextContent('owner');
  expect(items[0]).toHaveTextContent('active');
  expect(items[1]).toHaveTextContent('Juniper');
  expect(items[1]).toHaveTextContent('staff');
  expect(items[1]).toHaveTextContent('suspended');
});

test('an empty membership list renders the honest empty state', async () => {
  const client = makeClient({
    auth: {
      getSession: vi.fn(async () => ok(sessionView({ memberships: [] }))),
    },
  });
  renderApp('/', client);
  expect(
    await screen.findByText(/don't manage any restaurants yet/i),
  ).toBeInTheDocument();
});

test('a restaurant owner lands on their Restaurant Dashboard', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
  });
  renderApp('/', client);
  // The owner-facing landing is named for what it is, not "control center".
  expect(
    await screen.findByRole('heading', { name: /restaurant dashboard/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: /my restaurants/i }),
  ).toBeInTheDocument();
});

test('a platform administrator lands on a distinct Platform Administration home', async () => {
  const view = sessionView();
  view.user = { ...view.user, is_platform_admin: true };
  view.memberships = [];
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(view)) },
  });
  renderApp('/', client);
  // A platform admin's landing is not identical to an owner's: it is named
  // Platform Administration and points at the platform area (item 1).
  expect(
    await screen.findByRole('heading', { name: /platform administration/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('link', { name: /platform administration/i }),
  ).toHaveAttribute('href', '/platform');
});

test('logout sends the current CSRF token and clears session state', async () => {
  const logout = vi.fn(async () => ok({ status: 'logged_out' as const }));
  const client = authenticatedClient({ auth: { logout } });
  const { router } = renderApp('/', client);

  fireEvent.click(await screen.findByRole('button', { name: /sign out/i }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
  expect(logout).toHaveBeenCalledExactlyOnceWith('csrf-token-1');
  // Anonymous again: the sign-in form renders, no authenticated chrome.
  expect(
    await screen.findByRole('heading', { name: /^sign in$/i }),
  ).toBeInTheDocument();
  expect(screen.queryByText(/signed in as/i)).toBeNull();
});

test('a privileged 401 on logout clears state without a session refetch loop', async () => {
  const getSession = vi.fn(async () => ok(sessionView()));
  const logout = vi.fn(async () =>
    apiError(401, envelope('unauthorized', 'Authentication required.')),
  );
  const client = makeClient({ auth: { getSession, logout } });
  const { router } = renderApp('/', client);

  fireEvent.click(await screen.findByRole('button', { name: /sign out/i }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
  // The cache was *set* to anonymous — no refetch of a known-dead session.
  expect(getSession).toHaveBeenCalledTimes(1);
});

test('a non-401 logout failure keeps the session and reports the error', async () => {
  const logout = vi.fn(async () => apiError(503, null));
  const client = authenticatedClient({ auth: { logout } });
  const { router } = renderApp('/', client);

  fireEvent.click(await screen.findByRole('button', { name: /sign out/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /sign-out failed/i,
  );
  expect(router.state.location.pathname).toBe('/');
  expect(screen.getByText(/signed in as/i)).toBeInTheDocument();
});
