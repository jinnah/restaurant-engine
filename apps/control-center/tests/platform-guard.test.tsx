import { screen, waitFor, within } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import {
  adminSessionView,
  makeClient,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

test('a platform administrator reaches the platform overview', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
  });
  renderApp('/platform', client);

  expect(
    await screen.findByRole('heading', { name: /platform administration/i }),
  ).toBeInTheDocument();
  const nav = screen.getByRole('navigation', { name: /platform sections/i });
  expect(
    within(nav).getByRole('link', { name: /businesses/i }),
  ).toBeInTheDocument();
  expect(
    within(nav).getByRole('link', { name: /recovery/i }),
  ).toBeInTheDocument();
  expect(within(nav).getByRole('link', { name: /audit/i })).toBeInTheDocument();
});

test('an authenticated non-administrator gets not-found, never platform UI', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
  });
  const { router } = renderApp('/platform', client);

  expect(
    await screen.findByRole('heading', { name: /page not found/i }),
  ).toBeInTheDocument();
  // The URL is untouched (no redirect) and no platform content rendered.
  expect(router.state.location.pathname).toBe('/platform');
  expect(
    screen.queryByRole('heading', { name: /platform administration/i }),
  ).toBeNull();
});

test('an anonymous platform deep link goes to login preserving next', async () => {
  const { router } = renderApp('/platform', makeClient());
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
  expect(router.state.location.search).toBe(
    '?next=' + encodeURIComponent('/platform'),
  );
});

test('the primary navigation shows Platform only to administrators', async () => {
  const adminClient = makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
  });
  const adminRender = renderApp('/', adminClient);
  await screen.findByRole('heading', { name: /platform administration/i });
  expect(screen.getByRole('link', { name: /^platform$/i })).toBeInTheDocument();
  adminRender.view.unmount();

  const memberClient = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
  });
  renderApp('/', memberClient);
  await screen.findByRole('heading', { name: /restaurant dashboard/i });
  expect(screen.queryByRole('link', { name: /^platform$/i })).toBeNull();
});

test('an unknown platform child path renders not-found for administrators', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
  });
  renderApp('/platform/nonexistent', client);
  expect(
    await screen.findByRole('heading', { name: /page not found/i }),
  ).toBeInTheDocument();
});
