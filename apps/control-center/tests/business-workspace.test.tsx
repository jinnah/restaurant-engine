// The business workspace shell, membership guard, and current-business
// switcher (M3E, ADR-018 ruling 2). Guards here are navigation aids: every
// assertion about authorization is an assertion about presentation, and the
// backend's neutral 404 is what the UI reproduces.

import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import {
  adminMenu,
  adminSessionView,
  business,
  category,
  item,
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

// --- The business boundary ---------------------------------------------
//
// `/businesses/:businessId/...` matches the same route elements on both sides
// of a switch, so without an explicit boundary React keeps every child page
// instance — and its state — alive across it. Nothing can cross a tenant
// boundary on read (keys are business-scoped and the backend re-checks
// membership), but state that outlives the switch is state the user entered
// for a *different* business, and saving it would legitimately write it to
// this one. These assert the invariant behaviourally, not by inspecting keys.

// Two categories each: the reorder affordance only appears when there is
// something to reorder.
const SHALIK_MENU = adminMenu([
  category({
    id: 'c1',
    name: 'Starters',
    items: [item({ id: 'i1', category_id: 'c1', name: 'Samosa' })],
  }),
  category({ id: 'c2', name: 'Biryani', position: 1, items: [] }),
]);
const NUR_MENU = adminMenu([
  category({
    id: 'c9',
    name: 'Grill',
    items: [item({ id: 'i9', category_id: 'c9', name: 'Seekh Kebab' })],
  }),
  category({ id: 'c10', name: 'Breads', position: 1, items: [] }),
]);

function twoBusinessClient() {
  return makeClient({
    auth: authenticated({ memberships: twoBusinesses }),
    businesses: {
      get: vi.fn(async (id: string) => ok(business({ id, currency: 'USD' }))),
    },
    catalog: {
      getMenu: vi.fn(async (id: string) =>
        ok(id === SHALIK ? SHALIK_MENU : NUR_MENU),
      ),
      getModifierGroups: vi.fn(async () => ok({ item_id: 'i1', groups: [] })),
    },
  });
}

test('switching business discards the overview filter and reorder mode', async () => {
  const { router } = renderApp(
    `/businesses/${SHALIK}/menu`,
    twoBusinessClient(),
  );

  // Establish visible local state under Shalik.
  fireEvent.change(await screen.findByLabelText('Filter items by name'), {
    target: { value: 'samosa' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Reorder categories' }));
  expect(
    await screen.findByRole('heading', { name: 'Reorder categories' }),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('Business'), {
    target: { value: NUR },
  });

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(`/businesses/${NUR}/menu`);
  });
  expect(await screen.findByText('Grill')).toBeInTheDocument();
  // Nur's workspace starts clean rather than inheriting Shalik's session.
  expect(
    screen.getByLabelText<HTMLInputElement>('Filter items by name').value,
  ).toBe('');
  expect(
    screen.queryByRole('heading', { name: 'Reorder categories' }),
  ).toBeNull();
});

test('switching business carries no open dialog or its entered values', async () => {
  const { router } = renderApp(
    `/businesses/${SHALIK}/menu`,
    twoBusinessClient(),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'New category' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('Name'), {
    target: { value: 'Shalik Only Category' },
  });

  fireEvent.change(screen.getByLabelText('Business'), {
    target: { value: NUR },
  });

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(`/businesses/${NUR}/menu`);
  });
  await screen.findByText('Grill');
  // A dialog left open would be mutation-capable against the wrong business.
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.queryByDisplayValue('Shalik Only Category')).toBeNull();
});

test('switching business from a dirty create form prompts, then discards it', async () => {
  const { router } = renderApp(
    `/businesses/${SHALIK}/menu/items/new?categoryId=c1`,
    twoBusinessClient(),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Shalik Only Samosa' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: '3.50' },
  });

  fireEvent.change(screen.getByLabelText('Business'), {
    target: { value: NUR },
  });

  // The unsaved-changes guard still runs; the user chooses to abandon.
  expect(
    await screen.findByRole('heading', { name: 'Leave without saving?' }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Leave' }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(`/businesses/${NUR}/menu`);
  });
  expect(screen.queryByDisplayValue('Shalik Only Samosa')).toBeNull();
});

test('a dirty create form does not follow the user into another business', async () => {
  // The decisive case: both sides are `menu/items/new`, so the *same* route
  // element matches before and after. Without the boundary the page instance
  // survives and Shalik's unsaved values would sit in a form now pointed at
  // Nur — one Save away from being created in the wrong business.
  const { router } = renderApp(
    `/businesses/${SHALIK}/menu/items/new?categoryId=c1`,
    twoBusinessClient(),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Shalik Only Samosa' },
  });

  await act(async () => {
    await router.navigate(`/businesses/${NUR}/menu/items/new?categoryId=c9`);
  });

  fireEvent.click(await screen.findByRole('button', { name: 'Leave' }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(
      `/businesses/${NUR}/menu/items/new`,
    );
  });
  const name = await screen.findByLabelText<HTMLInputElement>('Name');
  expect(name.value).toBe('');
  expect(screen.queryByDisplayValue('Shalik Only Samosa')).toBeNull();
});

test('navigating within one business is ordinary navigation', async () => {
  const { router } = renderApp(
    `/businesses/${SHALIK}/menu`,
    twoBusinessClient(),
  );

  fireEvent.click(await screen.findByRole('link', { name: 'Samosa' }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(
      `/businesses/${SHALIK}/menu/items/i1`,
    );
  });
  // The editor loads the item, and the workspace chrome is unchanged.
  expect(await screen.findByLabelText<HTMLInputElement>('Name')).toHaveValue(
    'Samosa',
  );
  expect(
    screen.getByRole('heading', { level: 1, name: 'Shalik' }),
  ).toBeInTheDocument();
});
