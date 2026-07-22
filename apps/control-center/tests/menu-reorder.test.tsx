// Accessible reordering (M3E, ADR-018 ruling 5): move up, move down, and an
// explicit position, with no drag-and-drop anywhere.

import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
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
import { moveDown, moveTo, moveUp, sameOrder } from '../src/menu/reorder';

const SHALIK = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const MENU = `/businesses/${SHALIK}/menu`;

describe('permutation helpers', () => {
  const list = ['a', 'b', 'c'];

  test('moving keeps every element exactly once', () => {
    // The contract validates the submitted set against the stored set, so a
    // helper that dropped or duplicated an id would turn a UI slip into a 409.
    expect(moveUp(list, 1)).toEqual(['b', 'a', 'c']);
    expect(moveDown(list, 0)).toEqual(['b', 'a', 'c']);
    expect(moveTo(list, 0, 2)).toEqual(['b', 'c', 'a']);
    expect(moveTo(list, 2, 0)).toEqual(['c', 'a', 'b']);
  });

  test('an out-of-range move is a no-op, not an error', () => {
    expect(moveUp(list, 0)).toEqual(list);
    expect(moveDown(list, 2)).toEqual(list);
    expect(moveTo(list, 0, -1)).toEqual(list);
    expect(moveTo(list, 0, 99)).toEqual(list);
    expect(moveTo([], 0, 0)).toEqual([]);
  });

  test('the input is never mutated', () => {
    const original = [...list];
    moveUp(list, 1);
    expect(list).toEqual(original);
  });

  test('identical orders are recognised', () => {
    expect(sameOrder(['a', 'b'], ['a', 'b'])).toBe(true);
    expect(sameOrder(['a', 'b'], ['b', 'a'])).toBe(false);
    expect(sameOrder(['a'], ['a', 'b'])).toBe(false);
  });
});

function client(
  categories: Parameters<typeof adminMenu>[0],
  overrides: Parameters<typeof makeClient>[0] = {},
  role: 'owner' | 'staff' = 'owner',
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

const twoCategories = [
  category({ id: 'c1', name: 'Starters', position: 0 }),
  category({ id: 'c2', name: 'Biryani', position: 1 }),
];

const twoItems = [
  category({
    id: 'c1',
    name: 'Starters',
    items: [
      item({ id: 'i1', name: 'Samosa', position: 0 }),
      item({ id: 'i2', name: 'Beguni', position: 1 }),
    ],
  }),
];

test('categories reorder by keyboard and send the complete permutation', async () => {
  const reorderCategories = vi.fn(async () => ok(adminMenu(twoCategories)));
  renderApp(MENU, client(twoCategories, { catalog: { reorderCategories } }));

  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Move Biryani up' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save category order' }));

  await waitFor(() => {
    expect(reorderCategories).toHaveBeenCalledWith(
      SHALIK,
      { ordered_category_ids: ['c2', 'c1'] },
      'csrf-token-1',
    );
  });
  expect(await screen.findByText('Category order saved.')).toBeInTheDocument();
});

test('each move is announced', async () => {
  renderApp(MENU, client(twoCategories));
  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Move Biryani up' }));

  expect(
    await screen.findByText('Biryani moved to position 1 of 2.'),
  ).toBeInTheDocument();
});

test('the position field moves an entry directly', async () => {
  const reorderCategories = vi.fn(async () => ok(adminMenu(twoCategories)));
  renderApp(MENU, client(twoCategories, { catalog: { reorderCategories } }));

  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  );
  fireEvent.change(screen.getByLabelText('Position for Starters'), {
    target: { value: '2' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save category order' }));

  await waitFor(() => {
    expect(reorderCategories).toHaveBeenCalledWith(
      SHALIK,
      { ordered_category_ids: ['c2', 'c1'] },
      'csrf-token-1',
    );
  });
});

test('the first entry cannot move up and the last cannot move down', async () => {
  renderApp(MENU, client(twoCategories));
  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  );
  expect(
    screen.getByRole('button', { name: 'Move Starters up' }),
  ).toBeDisabled();
  expect(
    screen.getByRole('button', { name: 'Move Biryani down' }),
  ).toBeDisabled();
});

test('saving is disabled until the order actually changes', async () => {
  renderApp(MENU, client(twoCategories));
  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  );
  expect(
    screen.getByRole('button', { name: 'Save category order' }),
  ).toBeDisabled();

  fireEvent.click(screen.getByRole('button', { name: 'Move Biryani up' }));
  expect(
    screen.getByRole('button', { name: 'Save category order' }),
  ).toBeEnabled();
});

test('cancel leaves the stored order untouched', async () => {
  const reorderCategories = vi.fn(async () => ok(adminMenu(twoCategories)));
  renderApp(MENU, client(twoCategories, { catalog: { reorderCategories } }));

  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Move Biryani up' }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

  expect(reorderCategories).not.toHaveBeenCalled();
  expect(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  ).toBeInTheDocument();
});

test('items reorder within one category and carry that category id', async () => {
  const reorderItems = vi.fn(async () => ok(adminMenu(twoItems)));
  renderApp(MENU, client(twoItems, { catalog: { reorderItems } }));

  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder items in Starters' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Move Beguni up' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save item order' }));

  await waitFor(() => {
    expect(reorderItems).toHaveBeenCalledWith(
      SHALIK,
      { category_id: 'c1', ordered_item_ids: ['i2', 'i1'] },
      'csrf-token-1',
    );
  });
});

test('a stale inexact-set conflict explains and refreshes', async () => {
  const reorderCategories = vi.fn(async () =>
    apiError(
      409,
      envelope(
        'conflict',
        "the supplied ids do not exactly match the business's categories; refresh and retry",
      ),
    ),
  );
  const getMenu = vi.fn(async () => ok(adminMenu(twoCategories)));
  renderApp(
    MENU,
    client(twoCategories, { catalog: { reorderCategories, getMenu } }),
  );

  fireEvent.click(
    await screen.findByRole('button', { name: 'Reorder categories' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Move Biryani up' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save category order' }));

  expect(
    await screen.findByText(/changed while you were reordering/i),
  ).toBeInTheDocument();
  await waitFor(() => {
    expect(getMenu).toHaveBeenCalledTimes(2);
  });
});

test('reordering is disabled while a filter is active, and says why', async () => {
  renderApp(MENU, client(twoItems));
  fireEvent.change(await screen.findByLabelText(/filter items by name/i), {
    target: { value: 'sam' },
  });

  // A permutation over a filtered subset would be an inexact set.
  expect(
    screen.getByRole('button', { name: 'Reorder items in Starters' }),
  ).toBeDisabled();
  expect(screen.getByText('Clear the filter to reorder.')).toBeInTheDocument();
});

test('reordering is not offered for a single entry', async () => {
  renderApp(
    MENU,
    client([category({ id: 'c1', name: 'Only', items: [item()] })]),
  );
  await screen.findByText('Only');
  expect(
    screen.queryByRole('button', { name: 'Reorder categories' }),
  ).toBeNull();
  expect(screen.queryByRole('button', { name: /Reorder Only/ })).toBeNull();
});

test('staff are offered no reordering at all', async () => {
  renderApp(MENU, client(twoCategories, {}, 'staff'));
  await screen.findByText('Starters');
  expect(
    screen.queryByRole('button', { name: 'Reorder categories' }),
  ).toBeNull();
});
