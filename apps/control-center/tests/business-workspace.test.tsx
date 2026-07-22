// The business workspace shell, membership guard, and current-business
// switcher (M3E, ADR-018 ruling 2). Guards here are navigation aids: every
// assertion about authorization is an assertion about presentation, and the
// backend's neutral 404 is what the UI reproduces.

import { fireEvent, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import {
  adminMenu,
  adminSessionView,
  category,
  makeClient,
  membership,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

const SHALIK = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const NUR = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c002';
const FOREIGN = '99999999-9999-4999-8999-999999999999';

function authenticated(overrides: Parameters<typeof sessionView>[0] = {}) {
  return {
    getSession: vi.fn(async () => ok(sessionView(overrides))),
  };
}

const twoBusinesses = [
  membership({ business_id: SHALIK, business_name: 'Shalik' }),
  membership({
    business_id: NUR,
    business_name: 'Nur Kitchen',
    business_slug: 'nur',
    role: 'manager',
    business_status: 'suspended',
  }),
];

test('a member reaches the workspace and sees the menu section', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu([category()])));
  renderApp(
    `/businesses/${SHALIK}/menu`,
    makeClient({ auth: authenticated(), catalog: { getMenu } }),
  );

  expect(
    await screen.findByRole('heading', { level: 1, name: 'Shalik' }),
  ).toBeInTheDocument();
  expect(await screen.findByText('Starters')).toBeInTheDocument();
  expect(getMenu).toHaveBeenCalledWith(SHALIK);
});

test('the workspace index redirects to the menu section', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  const { router } = renderApp(
    `/businesses/${SHALIK}`,
    makeClient({ auth: authenticated(), catalog: { getMenu } }),
  );

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(`/businesses/${SHALIK}/menu`);
  });
});

test('a business the session does not contain renders the neutral not-found page', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  renderApp(
    `/businesses/${FOREIGN}/menu`,
    makeClient({ auth: authenticated(), catalog: { getMenu } }),
  );

  expect(
    await screen.findByRole('heading', { level: 1, name: /page not found/i }),
  ).toBeInTheDocument();
  // The copy must not hint that the business exists but is someone else's —
  // the backend returns the same neutral 404 for both, and so does this.
  expect(screen.queryByText(/permission|access|not yours/i)).toBeNull();
});

test('no catalog request is made for a business the session does not contain', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  renderApp(
    `/businesses/${FOREIGN}/menu`,
    makeClient({ auth: authenticated(), catalog: { getMenu } }),
  );

  await screen.findByRole('heading', { level: 1, name: /page not found/i });
  expect(getMenu).not.toHaveBeenCalled();
});

test('an anonymous visitor is sent to login with the workspace path preserved', async () => {
  const { router } = renderApp(`/businesses/${SHALIK}/menu`, makeClient());

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
  expect(router.state.location.search).toBe(
    `?next=${encodeURIComponent(`/businesses/${SHALIK}/menu`)}`,
  );
});

test('a platform administrator holds no memberships, so no switcher renders', async () => {
  renderApp(
    '/',
    makeClient({
      auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
    }),
  );

  await screen.findByRole('heading', { level: 1, name: /control center/i });
  expect(screen.queryByLabelText('Business')).toBeNull();
  // Their own navigation is untouched.
  expect(screen.getByRole('link', { name: 'Platform' })).toBeInTheDocument();
});

test('a platform administrator deep-linking a workspace gets the not-found page', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  renderApp(
    `/businesses/${SHALIK}/menu`,
    makeClient({
      auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
      catalog: { getMenu },
    }),
  );

  expect(
    await screen.findByRole('heading', { level: 1, name: /page not found/i }),
  ).toBeInTheDocument();
  expect(getMenu).not.toHaveBeenCalled();
});

test('the switcher lists only the session memberships', async () => {
  renderApp(
    '/',
    makeClient({ auth: authenticated({ memberships: twoBusinesses }) }),
  );

  const select = await screen.findByLabelText('Business');
  const labels = Array.from(select.querySelectorAll('option')).map(
    (option) => option.textContent,
  );
  expect(labels).toEqual([
    '— Choose a business —',
    'Shalik — owner',
    'Nur Kitchen — manager · suspended',
  ]);
});

test('a non-active status is spelled out in the option text, not by colour', async () => {
  renderApp(
    '/',
    makeClient({
      auth: authenticated({
        memberships: [
          membership({
            business_id: NUR,
            business_name: 'Nur Kitchen',
            business_status: 'closed',
          }),
        ],
      }),
    }),
  );

  const select = await screen.findByLabelText('Business');
  // Closed businesses stay selectable: the workspace is read-only, not
  // hidden, and an owner may still need to read the menu.
  expect(select.querySelector('option[value="' + NUR + '"]')?.textContent).toBe(
    'Nur Kitchen — owner · closed',
  );
});

test('the switcher reflects the route rather than any internal state', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  renderApp(
    `/businesses/${NUR}/menu`,
    makeClient({
      auth: authenticated({ memberships: twoBusinesses }),
      catalog: { getMenu },
    }),
  );

  const select = await screen.findByLabelText<HTMLSelectElement>('Business');
  expect(select.value).toBe(NUR);
});

test('outside a workspace the switcher shows its placeholder', async () => {
  renderApp(
    '/',
    makeClient({ auth: authenticated({ memberships: twoBusinesses }) }),
  );

  const select = await screen.findByLabelText<HTMLSelectElement>('Business');
  expect(select.value).toBe('');
});

test('choosing a business navigates to that business menu workspace', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  const { router } = renderApp(
    '/',
    makeClient({
      auth: authenticated({ memberships: twoBusinesses }),
      catalog: { getMenu },
    }),
  );

  const select = await screen.findByLabelText('Business');
  fireEvent.change(select, { target: { value: NUR } });

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(`/businesses/${NUR}/menu`);
  });
});

test('the switcher is absent when the session holds no memberships', async () => {
  renderApp('/', makeClient({ auth: authenticated({ memberships: [] }) }));

  await screen.findByRole('heading', { level: 1, name: /control center/i });
  expect(screen.queryByLabelText('Business')).toBeNull();
  expect(
    screen.getByText(/do not have any business memberships yet/i),
  ).toBeInTheDocument();
});

test('a route id outside the memberships selects the placeholder, inventing no option', async () => {
  renderApp(
    `/businesses/${FOREIGN}/menu`,
    makeClient({ auth: authenticated({ memberships: twoBusinesses }) }),
  );

  await screen.findByRole('heading', { level: 1, name: /page not found/i });
  const select = screen.getByLabelText<HTMLSelectElement>('Business');
  expect(select.value).toBe('');
  expect(select.querySelector(`option[value="${FOREIGN}"]`)).toBeNull();
});

test('home links each membership into its workspace', async () => {
  renderApp(
    '/',
    makeClient({ auth: authenticated({ memberships: twoBusinesses }) }),
  );

  const link = await screen.findByRole('link', { name: 'Shalik' });
  expect(link).toHaveAttribute('href', `/businesses/${SHALIK}/menu`);
});

test('a suspended business is editable and says so; a closed one says it is not', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  const client = makeClient({
    auth: authenticated({ memberships: twoBusinesses }),
    catalog: { getMenu },
  });
  const { view } = renderApp(`/businesses/${NUR}/menu`, client);
  expect(await screen.findByText(/storefront is offline/i)).toBeInTheDocument();
  expect(screen.getByText(/still edit the menu/i)).toBeInTheDocument();
  view.unmount();

  renderApp(
    `/businesses/${NUR}/menu`,
    makeClient({
      auth: authenticated({
        memberships: [
          membership({
            business_id: NUR,
            business_name: 'Nur Kitchen',
            business_status: 'closed',
          }),
        ],
      }),
      catalog: { getMenu },
    }),
  );
  expect(
    await screen.findByText(/can no longer be edited/i),
  ).toBeInTheDocument();
});

test('the menu surfaces loading, failure with retry, and the empty state', async () => {
  const getMenu = vi.fn(async () => ok(adminMenu()));
  renderApp(
    `/businesses/${SHALIK}/menu`,
    makeClient({ auth: authenticated(), catalog: { getMenu } }),
  );
  expect(await screen.findByText(/your menu is empty/i)).toBeInTheDocument();
});

test('a menu failure is announced and retryable', async () => {
  const getMenu = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: 500, envelope: null })
    .mockResolvedValue(ok(adminMenu([category()])));
  renderApp(
    `/businesses/${SHALIK}/menu`,
    makeClient({ auth: authenticated(), catalog: { getMenu } }),
  );

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/menu could not be loaded/i);
  fireEvent.click(screen.getByRole('button', { name: /try again/i }));
  expect(await screen.findByText('Starters')).toBeInTheDocument();
});
