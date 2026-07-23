// Item creation and editing (M3E): distinct request models, dirty-only
// updates, the separate availability command, the featured ceiling, and
// unsaved-change protection.

import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import {
  adminMenu,
  apiError,
  business,
  category,
  envelope,
  item,
  makeClient,
  membership,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

const SHALIK = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const MENU = `/businesses/${SHALIK}/menu`;
const CAT = 'c1';

function client(
  categories: Parameters<typeof adminMenu>[0],
  overrides: Parameters<typeof makeClient>[0] = {},
  role: 'owner' | 'manager' | 'staff' = 'owner',
) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(
          sessionView({
            memberships: [membership({ business_id: SHALIK, role })],
          }),
        ),
      ),
    },
    businesses: { get: vi.fn(async () => ok(business({ id: SHALIK }))) },
    ...overrides,
    catalog: {
      getMenu: vi.fn(async () => ok(adminMenu(categories))),
      ...overrides.catalog,
    },
  });
}

const oneCategory = [category({ id: CAT, name: 'Starters', items: [] })];

// --- Creation ----------------------------------------------------------

test('add item from a category preselects it', async () => {
  renderApp(`${MENU}/items/new?categoryId=${CAT}`, client(oneCategory));
  const select = await screen.findByLabelText<HTMLSelectElement>('Category');
  expect(select.value).toBe(CAT);
});

test('a missing categoryId stays recoverable through the selector', async () => {
  renderApp(`${MENU}/items/new`, client(oneCategory));
  const select = await screen.findByLabelText<HTMLSelectElement>('Category');
  expect(select.value).toBe('');
  expect(screen.getByRole('option', { name: 'Starters' })).toBeInTheDocument();
});

test('a stale categoryId explains itself and still lets the user continue', async () => {
  renderApp(`${MENU}/items/new?categoryId=deleted-one`, client(oneCategory));
  expect(
    await screen.findByText(/that category is no longer available/i),
  ).toBeInTheDocument();
  expect(screen.getByLabelText<HTMLSelectElement>('Category').value).toBe('');
});

test('the new-item route with no categories offers a category action, not an unsubmittable form (item 1)', async () => {
  renderApp(`${MENU}/items/new`, client([]));

  expect(
    await screen.findByText(
      /Create your first category before adding menu items/i,
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: 'Add a category' }),
  ).toBeInTheDocument();
  // The item form is withheld: there is nothing to file an item under yet.
  expect(screen.queryByLabelText('Name')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Add item' })).toBeNull();
});

test('creating the first category from the empty new-item route returns to the form with it selected (items 1, 3)', async () => {
  const createCategory = vi.fn(async () =>
    ok(category({ id: 'c-new', name: 'Sides' })),
  );
  const getMenu = vi
    .fn()
    .mockResolvedValueOnce(ok(adminMenu([])))
    .mockResolvedValue(
      ok(adminMenu([category({ id: 'c-new', name: 'Sides', items: [] })])),
    );
  renderApp(
    `${MENU}/items/new`,
    client([], { catalog: { getMenu, createCategory } }),
  );

  fireEvent.click(
    await screen.findByRole('button', { name: 'Add a category' }),
  );
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('Name'), {
    target: { value: 'Sides' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add category' }));

  await waitFor(() => {
    expect(createCategory).toHaveBeenCalledTimes(1);
  });
  // The refetched tree brings in the form, and the new category is chosen.
  const select = await screen.findByLabelText<HTMLSelectElement>('Category');
  await waitFor(() => {
    expect(select.value).toBe('c-new');
  });
  expect(screen.getByText(/Adding to:/)).toHaveTextContent('Sides');
});

const twoCategories = [
  category({ id: 'c1', name: 'River Fish', items: [] }),
  category({ id: 'c2', name: 'Drinks', items: [] }),
];

test('the add-item context names the chosen category and can be changed (item 4)', async () => {
  renderApp(`${MENU}/items/new?categoryId=c1`, client(twoCategories));

  const select = await screen.findByLabelText<HTMLSelectElement>('Category');
  expect(select.value).toBe('c1');
  expect(screen.getByText(/Adding to:/)).toHaveTextContent('River Fish');

  // The category stays changeable, and the visible context follows the choice.
  fireEvent.change(select, { target: { value: 'c2' } });
  expect(select.value).toBe('c2');
  expect(screen.getByText(/Adding to:/)).toHaveTextContent('Drinks');
});

test('add item from a different category preselects that category (item 4)', async () => {
  renderApp(`${MENU}/items/new?categoryId=c2`, client(twoCategories));
  const select = await screen.findByLabelText<HTMLSelectElement>('Category');
  expect(select.value).toBe('c2');
  expect(screen.getByText(/Adding to:/)).toHaveTextContent('Drinks');
});

test('a category can be created from the item form, selecting it and preserving what was typed (item 5)', async () => {
  const createCategory = vi.fn(async () =>
    ok(category({ id: 'c-new', name: 'Sides' })),
  );
  // The tree gains the new category on the post-create refetch, so the
  // selector can show it as chosen.
  const getMenu = vi
    .fn()
    .mockResolvedValueOnce(ok(adminMenu(oneCategory)))
    .mockResolvedValue(
      ok(adminMenu([...oneCategory, category({ id: 'c-new', name: 'Sides' })])),
    );
  renderApp(
    `${MENU}/items/new`,
    client(oneCategory, { catalog: { getMenu, createCategory } }),
  );

  // Enter item data first, with no category chosen.
  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Raita' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: '1.00' },
  });

  // Create a category inline, using the same dialog and validation.
  fireEvent.click(
    screen.getByRole('button', { name: '+ Create a new category' }),
  );
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('Name'), {
    target: { value: 'Sides' },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Add category' }));

  await waitFor(() => {
    expect(createCategory).toHaveBeenCalledTimes(1);
  });
  // The new category becomes the item's category, and nothing typed was lost.
  const select = await screen.findByLabelText<HTMLSelectElement>('Category');
  await waitFor(() => {
    expect(select.value).toBe('c-new');
  });
  expect(screen.getByLabelText<HTMLInputElement>('Name').value).toBe('Raita');
  expect(screen.getByLabelText<HTMLInputElement>(/^Price/).value).toBe('1.00');
});

test('creation sends only ItemCreate fields, with the category as a path argument', async () => {
  const createItem = vi.fn(async () =>
    ok(item({ id: 'new-1', name: 'Samosa' })),
  );
  renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, { catalog: { createItem } }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Samosa' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: '3.50' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add item' }));

  await waitFor(() => {
    expect(createItem).toHaveBeenCalledTimes(1);
  });
  expect(createItem).toHaveBeenCalledWith(
    SHALIK,
    CAT,
    {
      name: 'Samosa',
      description: null,
      price_minor: 350,
      dietary_tags: [],
    },
    'csrf-token-1',
  );
});

// --- The price ceiling belongs to the server ---------------------------

// The backend bound today. Named here only to prove the client does not
// enforce it; it is deliberately not imported from application code.
const FORMER_FRONTEND_CEILING_INPUT = '100000.01'; // 10,000,001 minor units

test('a price above the former frontend ceiling is sent, not blocked here', async () => {
  const createItem = vi.fn(async () => ok(item({ id: 'new-1', name: 'Gold' })));
  renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, { catalog: { createItem } }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Gold' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: FORMER_FRONTEND_CEILING_INPUT },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add item' }));

  // Reaches the API with the exact integer, for the server to rule on.
  await waitFor(() => {
    expect(createItem).toHaveBeenCalledTimes(1);
  });
  expect(createItem).toHaveBeenCalledWith(
    SHALIK,
    CAT,
    expect.objectContaining({ price_minor: 10_000_001 }),
    'csrf-token-1',
  );
  // And nothing here claimed a maximum on the way past.
  expect(screen.queryByText(/maximum|at most|higher than|allows/i)).toBeNull();
});

test("the server's price rejection is shown on the price field", async () => {
  const createItem = vi.fn(async () =>
    apiError(422, {
      error: {
        code: 'validation_error',
        message: 'The request was invalid.',
        correlation_id: null,
        field_errors: [
          {
            field: 'body.price_minor',
            message: 'Input should be less than or equal to 10000000',
          },
        ],
        details: null,
      },
    } as never),
  );
  renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, { catalog: { createItem } }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Gold' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: FORMER_FRONTEND_CEILING_INPUT },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add item' }));

  // The authoritative message, verbatim, on the input it was about — the
  // only way the real ceiling can reach the user now.
  expect(
    await screen.findByText('Input should be less than or equal to 10000000'),
  ).toBeInTheDocument();
  expect(await screen.findByRole('alert')).toHaveTextContent(
    /some fields need attention/i,
  );
});

test('local syntax, precision, sign and safety checks still block first', async () => {
  const createItem = vi.fn(async () => ok(item({ id: 'x' })));
  renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, { catalog: { createItem } }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Samosa' },
  });
  const price = screen.getByLabelText(/^Price/);

  // Anchored past the field's own hint ("Digits and a dot, for example
  // 12.50."), which would otherwise match the malformed message too.
  for (const [value, expected] of [
    ['abc', /enter a price using digits and a dot/i],
    ['1,50', /enter a price using digits and a dot/i],
    ['-1', /cannot be negative/i],
    ['1.234', /use at most 2 decimal places/i],
    ['999999999999999999.99', /too long to convert exactly/i],
    ['', /^Enter a price\.$/],
  ] as const) {
    fireEvent.change(price, { target: { value } });
    fireEvent.click(screen.getByRole('button', { name: 'Add item' }));
    expect(await screen.findByText(expected)).toBeInTheDocument();
  }

  // Not one of them reached the API.
  expect(createItem).not.toHaveBeenCalled();
});

test('the create form offers no update-only controls', async () => {
  renderApp(`${MENU}/items/new?categoryId=${CAT}`, client(oneCategory));
  await screen.findByLabelText('Name');
  expect(screen.queryByLabelText(/hide from the public menu/i)).toBeNull();
  expect(screen.queryByLabelText(/feature this item/i)).toBeNull();
  expect(screen.queryByRole('button', { name: /sold out/i })).toBeNull();
  // The defaults are explained rather than faked with inert controls.
  expect(
    screen.getByText(/new items start visible and available/i),
  ).toBeInTheDocument();
});

test('creation navigates to the canonical item URL, replacing history', async () => {
  const created = item({ id: 'new-1', name: 'Samosa', category_id: CAT });
  const createItem = vi.fn(async () => ok(created));
  const getMenu = vi
    .fn()
    .mockResolvedValueOnce(ok(adminMenu(oneCategory)))
    .mockResolvedValue(
      ok(
        adminMenu([category({ id: CAT, name: 'Starters', items: [created] })]),
      ),
    );
  const { router } = renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, { catalog: { createItem, getMenu } }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Samosa' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: '3.50' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add item' }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe(`${MENU}/items/new-1`);
  });
  // replace:true — Back returns to the menu, not to the create form.
  expect(router.state.historyAction).toBe('REPLACE');
  expect(await screen.findByText(/Item .Samosa. added/)).toBeInTheDocument();
});

test('a successful creation does not trigger the unsaved-changes prompt', async () => {
  const created = item({ id: 'new-1', name: 'Samosa', category_id: CAT });
  renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, {
      catalog: { createItem: vi.fn(async () => ok(created)) },
    }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Samosa' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: '3.50' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add item' }));

  await screen.findByText(/Item .Samosa. added/);
  expect(screen.queryByText(/leave without saving/i)).toBeNull();
});

test('cancel returns to the overview without creating anything', async () => {
  const createItem = vi.fn(async () => ok(item()));
  const { router } = renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, { catalog: { createItem } }),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
  await waitFor(() => {
    expect(router.state.location.pathname).toBe(MENU);
  });
  expect(createItem).not.toHaveBeenCalled();
});

test('leaving a dirty create form asks first', async () => {
  const { router } = renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Half typed' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

  expect(await screen.findByText(/leave without saving/i)).toBeInTheDocument();
  expect(router.state.location.pathname).toBe(`${MENU}/items/new`);

  fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
  await waitFor(() => {
    expect(router.state.location.pathname).toBe(MENU);
  });
});

test('an invalid price is refused before any request', async () => {
  const createItem = vi.fn(async () => ok(item()));
  renderApp(
    `${MENU}/items/new?categoryId=${CAT}`,
    client(oneCategory, { catalog: { createItem } }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Samosa' },
  });
  fireEvent.change(screen.getByLabelText(/^Price/), {
    target: { value: '3.501' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add item' }));

  expect(
    await screen.findByText(/use at most 2 decimal places/i),
  ).toBeInTheDocument();
  expect(createItem).not.toHaveBeenCalled();
});

// --- Editing -----------------------------------------------------------

const existing = item({
  id: 'i1',
  category_id: CAT,
  name: 'Samosa',
  description: 'Crisp pastry',
  price_minor: 350,
});
const withItem = [category({ id: CAT, name: 'Starters', items: [existing] })];

test('editing sends only the changed fields', async () => {
  const updateItem = vi.fn(async () => ok({ ...existing, name: 'Samosas' }));
  renderApp(`${MENU}/items/i1`, client(withItem, { catalog: { updateItem } }));

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Samosas' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => {
    expect(updateItem).toHaveBeenCalledTimes(1);
  });
  expect(updateItem).toHaveBeenCalledWith(
    SHALIK,
    'i1',
    { name: 'Samosas' },
    'csrf-token-1',
  );
});

test('an item update never carries is_available', async () => {
  const updateItem = vi.fn(async () => ok({ ...existing, is_hidden: true }));
  renderApp(`${MENU}/items/i1`, client(withItem, { catalog: { updateItem } }));

  fireEvent.click(await screen.findByLabelText(/hide from the public menu/i));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => {
    expect(updateItem).toHaveBeenCalledTimes(1);
  });
  expect(updateItem).toHaveBeenCalledWith(
    SHALIK,
    'i1',
    { is_hidden: true },
    'csrf-token-1',
  );
});

test('save is disabled until something changes', async () => {
  renderApp(`${MENU}/items/i1`, client(withItem));
  expect(
    await screen.findByRole('button', { name: 'Save changes' }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Samosas' },
  });
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
});

test('a price round-trips through the editable form', async () => {
  renderApp(`${MENU}/items/i1`, client(withItem));
  const price = await screen.findByLabelText<HTMLInputElement>(/^Price/);
  expect(price.value).toBe('3.50');
});

test('the availability command is separate from the form', async () => {
  const setItemAvailability = vi.fn(async () =>
    ok({ ...existing, is_available: false }),
  );
  const updateItem = vi.fn(async () => ok(existing));
  renderApp(
    `${MENU}/items/i1`,
    client(withItem, { catalog: { setItemAvailability, updateItem } }),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Mark sold out' }));

  await waitFor(() => {
    expect(setItemAvailability).toHaveBeenCalledWith(
      SHALIK,
      'i1',
      { is_available: false },
      'csrf-token-1',
    );
  });
  expect(updateItem).not.toHaveBeenCalled();
  expect(await screen.findByText(/marked sold out/i)).toBeInTheDocument();
});

test('staff can toggle availability but cannot edit the item', async () => {
  renderApp(`${MENU}/items/i1`, client(withItem, {}, 'staff'));

  expect(
    await screen.findByRole('button', { name: 'Mark sold out' }),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText('Name')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Save changes' })).toBeNull();
  expect(
    screen.queryByRole('button', { name: /delete this item/i }),
  ).toBeNull();
  expect(screen.getByText(/needs a manager or owner/i)).toBeInTheDocument();
});

test('the featured count is shown, but no ceiling the contract never gave', async () => {
  renderApp(`${MENU}/items/i1`, client(withItem));

  // The count is real and comes from the tree. The ceiling is a service-side
  // count limit that JSON Schema cannot express, so it is absent from the
  // generated contract and must not be asserted until the server states it.
  const hint = await screen.findByText(/Featured so far: 0/);
  expect(hint).toHaveTextContent(/There is a limit/);
  expect(hint).not.toHaveTextContent(/of \d/);
});

test('a featured-limit conflict reverts, quotes the server limit, and refetches', async () => {
  const updateItem = vi.fn(async () =>
    apiError(409, {
      error: {
        code: 'conflict',
        message: 'Featured item limit reached.',
        correlation_id: null,
        field_errors: [],
        details: { limit: 6 },
      },
    } as never),
  );
  const getMenu = vi.fn(async () => ok(adminMenu(withItem)));
  renderApp(
    `${MENU}/items/i1`,
    client(withItem, { catalog: { updateItem, getMenu } }),
  );

  fireEvent.click(await screen.findByLabelText(/feature this item/i));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  expect(
    await screen.findByText(/You can feature at most 6 items/),
  ).toBeInTheDocument();
  // The attempted state is reverted rather than left looking applied.
  await waitFor(() => {
    expect(
      screen.getByLabelText<HTMLInputElement>(/feature this item/i).checked,
    ).toBe(false);
  });
  await waitFor(() => {
    expect(getMenu).toHaveBeenCalledTimes(2);
  });
});

test('whatever limit the server states is simply adopted', async () => {
  const updateItem = vi.fn(async () =>
    apiError(409, {
      error: {
        code: 'conflict',
        message: 'Featured item limit reached.',
        correlation_id: null,
        field_errors: [],
        details: { limit: 8 },
      },
    } as never),
  );
  renderApp(`${MENU}/items/i1`, client(withItem, { catalog: { updateItem } }));

  fireEvent.click(await screen.findByLabelText(/feature this item/i));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  // There is no client-side expectation for this number to disagree with, so
  // 8 is not "drift" to be reported — it is simply the limit, stated by the
  // only party that knows it.
  expect(
    await screen.findByText(/You can feature at most 8 items/),
  ).toBeInTheDocument();
  // And it is what the page shows from then on.
  expect(
    await screen.findByText(/Featured: 0 of 8\. Hidden items count/),
  ).toBeInTheDocument();
});

test('an item that vanished mid-edit explains and refreshes', async () => {
  const updateItem = vi.fn(async () =>
    apiError(404, envelope('not_found', 'Not found.')),
  );
  const getMenu = vi.fn(async () => ok(adminMenu(withItem)));
  renderApp(
    `${MENU}/items/i1`,
    client(withItem, { catalog: { updateItem, getMenu } }),
  );

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Samosas' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  expect(
    await screen.findByText(
      /was changed or removed. The menu has been refreshed/i,
    ),
  ).toBeInTheDocument();
  await waitFor(() => {
    expect(getMenu).toHaveBeenCalledTimes(2);
  });
});

test('an unknown item id renders the neutral not-found page', async () => {
  renderApp(`${MENU}/items/does-not-exist`, client(withItem));
  expect(
    await screen.findByRole('heading', { level: 1, name: /page not found/i }),
  ).toBeInTheDocument();
});

test('deleting an item confirms, states the cascade, and returns to the menu', async () => {
  const deleteItem = vi.fn(async () => ok({ status: 'deleted' as const }));
  const { router } = renderApp(
    `${MENU}/items/i1`,
    client(withItem, { catalog: { deleteItem } }),
  );

  fireEvent.click(
    await screen.findByRole('button', { name: /delete this item/i }),
  );
  expect(
    screen.getByText(/its options are deleted with it/i),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/photo stays in your image library/i),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Delete item' }));

  await waitFor(() => {
    expect(deleteItem).toHaveBeenCalledWith(SHALIK, 'i1', 'csrf-token-1');
  });
  await waitFor(() => {
    expect(router.state.location.pathname).toBe(MENU);
  });
});

test('leaving a dirty editor asks first', async () => {
  const { router } = renderApp(`${MENU}/items/i1`, client(withItem));

  fireEvent.change(await screen.findByLabelText('Name'), {
    target: { value: 'Changed' },
  });
  fireEvent.click(screen.getByRole('link', { name: /back to the menu/i }));

  expect(await screen.findByText(/unsaved changes/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(router.state.location.pathname).toBe(`${MENU}/items/i1`);
});

test('the overview offers the availability toggle to staff and links to the editor', async () => {
  renderApp(MENU, client(withItem, {}, 'staff'));
  expect(
    await screen.findByRole('button', { name: 'Mark sold out' }),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Samosa' })).toHaveAttribute(
    'href',
    `${MENU}/items/i1`,
  );
  // Staff still get no create affordance.
  expect(screen.queryByRole('link', { name: /add item to/i })).toBeNull();
});

test('each item row offers a Manage action that opens that item for that restaurant (items 6, 9)', async () => {
  renderApp(MENU, client(withItem));
  // The action names the item, so it is distinguishable out of context, and
  // points at the same editor route scoped to this business.
  const manage = await screen.findByRole('link', { name: 'Manage Samosa' });
  expect(manage).toHaveAttribute('href', `${MENU}/items/i1`);
});

test('staff, who cannot edit, are not offered Manage — only the availability toggle (item 6)', async () => {
  renderApp(MENU, client(withItem, {}, 'staff'));
  await screen.findByText('Samosa');
  expect(screen.queryByRole('link', { name: /Manage Samosa/ })).toBeNull();
  expect(
    screen.getByRole('button', { name: 'Mark sold out' }),
  ).toBeInTheDocument();
});
