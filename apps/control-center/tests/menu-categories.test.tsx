// Category administration (M3E): create, edit, delete, and the honest
// handling of the conflicts the catalog service can return.

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

/**
 * Confirm a category create from inside its dialog.
 *
 * "Add category" is deliberately the consistent label for both the toolbar
 * trigger and the dialog's confirm (item 3), so once the dialog is open the
 * name resolves twice — the confirm is the one inside the dialog.
 */
function submitCategoryDialog() {
  fireEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', {
      name: 'Add category',
    }),
  );
}

const SHALIK = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const MENU = `/businesses/${SHALIK}/menu`;

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

test('a category is created and confirmed after the dialog closes', async () => {
  const createCategory = vi.fn(async () =>
    ok({ ...category({ name: 'Biryani' }), items: undefined }),
  );
  renderApp(MENU, client([], { catalog: { createCategory } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add category' }));
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: '  Biryani  ' },
  });
  submitCategoryDialog();

  await waitFor(() => {
    expect(createCategory).toHaveBeenCalledTimes(1);
  });
  // The name is trimmed client-side; the server normalizes further and its
  // response is what gets rendered.
  expect(createCategory).toHaveBeenCalledWith(
    SHALIK,
    { name: 'Biryani', description: null },
    'csrf-token-1',
  );

  // The dialog must be gone before the confirmation appears, or the
  // notification would sit behind a focus trap.
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  expect(
    await screen.findByText(/Category .Biryani. added/),
  ).toBeInTheDocument();
});

test('a blank name is caught before any request is made', async () => {
  const createCategory = vi.fn(async () => ok(category()));
  renderApp(MENU, client([], { catalog: { createCategory } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add category' }));
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: '   ' } });
  submitCategoryDialog();

  expect(
    await screen.findByText('Enter a name for this category.'),
  ).toBeInTheDocument();
  expect(createCategory).not.toHaveBeenCalled();
});

test('a duplicate-name conflict lands on the name field', async () => {
  const createCategory = vi.fn(async () =>
    apiError(
      409,
      envelope('conflict', 'a category with this name already exists', [
        { field: 'body.name', code: 'conflict', message: 'Already used.' },
      ]),
    ),
  );
  renderApp(MENU, client([], { catalog: { createCategory } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add category' }));
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Starters' },
  });
  submitCategoryDialog();

  expect(await screen.findByText('Already used.')).toBeInTheDocument();
  // The dialog stays open so nothing typed is lost.
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('editing sends only the fields that changed', async () => {
  const updateCategory = vi.fn(async () =>
    ok(category({ name: 'Small plates' })),
  );
  renderApp(
    MENU,
    client([category({ id: 'c1', name: 'Starters', description: 'Nibbles' })], {
      catalog: { updateCategory },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: /Edit Starters/ }));
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Small plates' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => {
    expect(updateCategory).toHaveBeenCalledTimes(1);
  });
  // description and is_visible are untouched, so they must not be sent: a
  // PATCH that resends them would clobber a concurrent edit.
  expect(updateCategory).toHaveBeenCalledWith(
    SHALIK,
    'c1',
    { name: 'Small plates' },
    'csrf-token-1',
  );
});

test('a visibility change alone is sent alone', async () => {
  const updateCategory = vi.fn(async () => ok(category()));
  renderApp(
    MENU,
    client([category({ id: 'c1', name: 'Starters' })], {
      catalog: { updateCategory },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: /Edit Starters/ }));
  fireEvent.click(screen.getByLabelText('Visible on the storefront'));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => {
    expect(updateCategory).toHaveBeenCalledTimes(1);
  });
  expect(updateCategory).toHaveBeenCalledWith(
    SHALIK,
    'c1',
    { is_visible: false },
    'csrf-token-1',
  );
});

test('an unchanged edit closes without calling the server', async () => {
  const updateCategory = vi.fn(async () => ok(category()));
  renderApp(
    MENU,
    client([category({ id: 'c1', name: 'Starters' })], {
      catalog: { updateCategory },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: /Edit Starters/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  expect(updateCategory).not.toHaveBeenCalled();
});

test('deleting is offered only for an empty category and is confirmed', async () => {
  const deleteCategory = vi.fn(async () => ok({ status: 'deleted' as const }));
  renderApp(
    MENU,
    client(
      [
        category({ id: 'c1', name: 'Empty', items: [] }),
        category({ id: 'c2', name: 'Full', items: [item()] }),
      ],
      { catalog: { deleteCategory } },
    ),
  );

  // Delete is offered only where it can succeed — the empty category — so a
  // non-empty one shows no dead disabled control and no persistent note
  // (item 6). The empty one's Delete is present and reachable.
  await screen.findByRole('button', { name: /Delete Empty/ });
  expect(screen.queryByRole('button', { name: /Delete Full/ })).toBeNull();
  expect(screen.queryByText(/Move or delete its items/)).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: /Delete Empty/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Delete category' }));

  await waitFor(() => {
    expect(deleteCategory).toHaveBeenCalledWith(SHALIK, 'c1', 'csrf-token-1');
  });
  expect(
    await screen.findByText(/Category .Empty. deleted/),
  ).toBeInTheDocument();
});

test('a stale non-empty conflict explains and refetches instead of failing silently', async () => {
  const deleteCategory = vi.fn(async () =>
    apiError(
      409,
      envelope(
        'conflict',
        'the category is not empty; move or delete its items first',
      ),
    ),
  );
  const getMenu = vi.fn(async () =>
    ok(adminMenu([category({ id: 'c1', name: 'Empty' })])),
  );
  renderApp(
    MENU,
    client([category({ id: 'c1', name: 'Empty', items: [] })], {
      catalog: { deleteCategory, getMenu },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: /Delete Empty/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Delete category' }));

  expect(
    await screen.findByText(/the category is not empty/i),
  ).toBeInTheDocument();
  await waitFor(() => {
    expect(getMenu).toHaveBeenCalledTimes(2); // initial load plus the refetch
  });
});

test('staff see no category write affordances at all', async () => {
  renderApp(
    MENU,
    client([category({ name: 'Starters', items: [item()] })], {}, 'staff'),
  );

  await screen.findByText('Starters');
  expect(screen.queryByRole('button', { name: 'Add category' })).toBeNull();
  expect(screen.queryByRole('button', { name: /Edit Starters/ })).toBeNull();
  expect(screen.queryByRole('button', { name: /Delete Starters/ })).toBeNull();
});

test('a closed business offers no category writes to an owner either', async () => {
  renderApp(
    MENU,
    makeClient({
      auth: {
        getSession: vi.fn(async () =>
          ok(
            sessionView({
              memberships: [
                membership({ business_id: SHALIK, business_status: 'closed' }),
              ],
            }),
          ),
        ),
      },
      businesses: {
        get: vi.fn(async () => ok(business({ id: SHALIK, status: 'closed' }))),
      },
      catalog: {
        getMenu: vi.fn(async () =>
          ok(adminMenu([category({ name: 'Starters' })])),
        ),
      },
    }),
  );

  await screen.findByText('Starters');
  expect(screen.queryByRole('button', { name: 'Add category' })).toBeNull();
});
