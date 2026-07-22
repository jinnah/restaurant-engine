// Modifier groups and options (M3E). Satisfiability is the server's
// computation and is strictly advisory here: a legal but unsatisfiable
// configuration is always storable (ADR-017 ruling D5).

import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import {
  adminMenu,
  business,
  category,
  item,
  makeClient,
  membership,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';
import { ruleSummary, unsatisfiableReason } from '../src/menu/modifierRules';

const SHALIK = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const MENU = `/businesses/${SHALIK}/menu`;
const EDITOR = `${MENU}/items/i1`;

const existing = item({ id: 'i1', category_id: 'c1', name: 'Samosa' });
const tree = [category({ id: 'c1', name: 'Starters', items: [existing] })];

function group(overrides: Record<string, unknown> = {}) {
  return {
    id: 'g1',
    item_id: 'i1',
    name: 'Choose a side',
    min_select: 0,
    max_select: null,
    position: 0,
    active_option_count: 1,
    is_satisfiable: true,
    options: [
      {
        id: 'o1',
        group_id: 'g1',
        name: 'Chutney',
        price_delta_minor: 0,
        is_available: true,
        position: 0,
        created_at: '2026-07-21T00:00:00Z',
        updated_at: '2026-07-21T00:00:00Z',
      },
    ],
    created_at: '2026-07-21T00:00:00Z',
    updated_at: '2026-07-21T00:00:00Z',
    ...overrides,
  };
}

function client(
  groups: ReturnType<typeof group>[],
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
      getMenu: vi.fn(async () => ok(adminMenu(tree))),
      getModifierGroups: vi.fn(async () => ok({ item_id: 'i1', groups })),
      ...overrides.catalog,
    },
  });
}

describe('rule summaries read as plain language', () => {
  test('optional and required shapes', () => {
    expect(ruleSummary({ min_select: 0, max_select: null })).toBe(
      'Optional — choose any number',
    );
    expect(ruleSummary({ min_select: 0, max_select: 1 })).toBe(
      'Optional — choose at most 1',
    );
    expect(ruleSummary({ min_select: 0, max_select: 3 })).toBe(
      'Optional — choose up to 3',
    );
    expect(ruleSummary({ min_select: 1, max_select: 1 })).toBe(
      'Required — choose exactly 1',
    );
    expect(ruleSummary({ min_select: 1, max_select: 3 })).toBe(
      'Required — choose 1 to 3',
    );
    expect(ruleSummary({ min_select: 2, max_select: null })).toBe(
      'Required — choose at least 2',
    );
  });
});

describe('unsatisfiable explanations follow the server numbers', () => {
  test('a satisfiable group has nothing to say', () => {
    expect(unsatisfiableReason(group() as never)).toBeNull();
  });

  test('a required group names the ordering consequence', () => {
    const reason = unsatisfiableReason(
      group({
        min_select: 1,
        active_option_count: 0,
        is_satisfiable: false,
        options: [],
      }) as never,
    );
    expect(reason).toContain('No options are available');
    expect(reason).toContain('cannot order this item');
  });

  test('an optional group is only omitted, never blocking', () => {
    const reason = unsatisfiableReason(
      group({
        min_select: 0,
        active_option_count: 0,
        is_satisfiable: false,
        options: [],
      }) as never,
    );
    expect(reason).toContain('left off your public menu');
  });

  test('a minimum above the available count is explained with both numbers', () => {
    const reason = unsatisfiableReason(
      group({
        min_select: 3,
        active_option_count: 1,
        is_satisfiable: false,
      }) as never,
    );
    expect(reason).toContain('at least 3');
    expect(reason).toContain('only 1');
  });
});

test('groups render with their rule, count, and options', async () => {
  renderApp(EDITOR, client([group({ min_select: 1, max_select: 1 })]));
  expect(
    await screen.findByRole('heading', { name: 'Choose a side' }),
  ).toBeInTheDocument();
  expect(screen.getByText('Required — choose exactly 1')).toBeInTheDocument();
  expect(screen.getByText('1 available choice')).toBeInTheDocument();
  expect(screen.getByText('Chutney')).toBeInTheDocument();
  expect(screen.getByText('No extra charge')).toBeInTheDocument();
});

test('an item with no groups explains what groups are for', async () => {
  renderApp(EDITOR, client([]));
  expect(await screen.findByText(/no option groups/i)).toBeInTheDocument();
});

test('there is no way to attach an existing group — none exists to attach', async () => {
  renderApp(EDITOR, client([group()]));
  await screen.findByRole('heading', { name: 'Choose a side' });
  expect(screen.queryByRole('button', { name: /attach/i })).toBeNull();
  expect(screen.queryByRole('button', { name: /existing group/i })).toBeNull();
});

test('creating a group sends the required minimum and an explicit unlimited maximum', async () => {
  const createModifierGroup = vi.fn(async () => ok(group({ name: 'Spice' })));
  renderApp(EDITOR, client([], { catalog: { createModifierGroup } }));

  fireEvent.click(await screen.findByRole('button', { name: 'New group' }));
  fireEvent.change(screen.getByLabelText('Group name'), {
    target: { value: 'Spice level' },
  });
  fireEvent.click(
    screen.getByLabelText(/the customer must choose from this group/i),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Add group' }));

  await waitFor(() => {
    expect(createModifierGroup).toHaveBeenCalledWith(
      SHALIK,
      'i1',
      // max_select null is the explicit "unlimited" the contract asks for.
      { name: 'Spice level', min_select: 1, max_select: null },
      'csrf-token-1',
    );
  });
});

test('clearing "no maximum" sends a finite maximum', async () => {
  const createModifierGroup = vi.fn(async () => ok(group()));
  renderApp(EDITOR, client([], { catalog: { createModifierGroup } }));

  fireEvent.click(await screen.findByRole('button', { name: 'New group' }));
  fireEvent.change(screen.getByLabelText('Group name'), {
    target: { value: 'Sides' },
  });
  fireEvent.click(screen.getByLabelText('No maximum'));
  fireEvent.change(screen.getByLabelText('Maximum choices'), {
    target: { value: '2' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add group' }));

  await waitFor(() => {
    expect(createModifierGroup).toHaveBeenCalledWith(
      SHALIK,
      'i1',
      { name: 'Sides', min_select: 0, max_select: 2 },
      'csrf-token-1',
    );
  });
});

test('a minimum above the maximum is refused before any request', async () => {
  const createModifierGroup = vi.fn(async () => ok(group()));
  renderApp(EDITOR, client([], { catalog: { createModifierGroup } }));

  fireEvent.click(await screen.findByRole('button', { name: 'New group' }));
  fireEvent.change(screen.getByLabelText('Group name'), {
    target: { value: 'Sides' },
  });
  fireEvent.click(
    screen.getByLabelText(/the customer must choose from this group/i),
  );
  fireEvent.change(screen.getByLabelText('Minimum choices'), {
    target: { value: '3' },
  });
  fireEvent.click(screen.getByLabelText('No maximum'));
  fireEvent.change(screen.getByLabelText('Maximum choices'), {
    target: { value: '2' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add group' }));

  expect(
    await screen.findByText(/minimum cannot be more than the maximum/i),
  ).toBeInTheDocument();
  expect(createModifierGroup).not.toHaveBeenCalled();
});

test('an unsatisfiable group shows the advisory and still allows editing', async () => {
  const updateModifierGroup = vi.fn(async () => ok(group()));
  renderApp(
    EDITOR,
    client(
      [
        group({
          min_select: 1,
          active_option_count: 0,
          is_satisfiable: false,
          options: [],
        }),
      ],
      { catalog: { updateModifierGroup } },
    ),
  );

  expect(
    await screen.findByText(/not currently selectable/i),
  ).toBeInTheDocument();

  // Advisory only: the group is still fully editable and savable.
  fireEvent.click(
    screen.getByRole('button', { name: 'Edit group Choose a side' }),
  );
  fireEvent.change(screen.getByLabelText('Group name'), {
    target: { value: 'Choose a sauce' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save group' }));

  await waitFor(() => {
    expect(updateModifierGroup).toHaveBeenCalledTimes(1);
  });
});

test('option availability rides the option update, with no separate command', async () => {
  const updateModifierOption = vi.fn(async () => ok(group()));
  renderApp(EDITOR, client([group()], { catalog: { updateModifierOption } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Edit Chutney' }));
  fireEvent.click(screen.getByLabelText('Available'));
  fireEvent.click(screen.getByRole('button', { name: 'Save choice' }));

  await waitFor(() => {
    expect(updateModifierOption).toHaveBeenCalledWith(
      SHALIK,
      'o1',
      { name: 'Chutney', price_delta_minor: 0, is_available: false },
      'csrf-token-1',
    );
  });
});

test('an option price delta is parsed as integer minor units', async () => {
  const createModifierOption = vi.fn(async () => ok(group()));
  renderApp(EDITOR, client([group()], { catalog: { createModifierOption } }));

  fireEvent.click(
    await screen.findByRole('button', {
      name: 'Add a choice to Choose a side',
    }),
  );
  fireEvent.change(screen.getByLabelText('Choice name'), {
    target: { value: 'Extra chutney' },
  });
  fireEvent.change(screen.getByLabelText(/extra charge/i), {
    target: { value: '0.75' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add choice' }));

  await waitFor(() => {
    expect(createModifierOption).toHaveBeenCalledWith(
      SHALIK,
      'g1',
      { name: 'Extra chutney', price_delta_minor: 75 },
      'csrf-token-1',
    );
  });
});

test('an unavailable option is marked in the list', async () => {
  renderApp(
    EDITOR,
    client([
      group({
        active_option_count: 0,
        is_satisfiable: false,
        options: [
          {
            id: 'o1',
            group_id: 'g1',
            name: 'Chutney',
            price_delta_minor: 0,
            is_available: false,
            position: 0,
            created_at: '2026-07-21T00:00:00Z',
            updated_at: '2026-07-21T00:00:00Z',
          },
        ],
      }),
    ]),
  );
  expect(await screen.findByText('Unavailable')).toBeInTheDocument();
});

test('deleting a group states the cascade with a real count', async () => {
  const deleteModifierGroup = vi.fn(async () =>
    ok({ status: 'deleted' as const }),
  );
  renderApp(EDITOR, client([group()], { catalog: { deleteModifierGroup } }));

  fireEvent.click(
    await screen.findByRole('button', { name: 'Delete group Choose a side' }),
  );
  expect(
    screen.getByText(/its 1 choice is deleted with it/i),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Delete group' }));

  await waitFor(() => {
    expect(deleteModifierGroup).toHaveBeenCalledWith(
      SHALIK,
      'g1',
      'csrf-token-1',
    );
  });
});

test('deleting the last available choice warns without preventing it', async () => {
  const deleteModifierOption = vi.fn(async () => ok(group()));
  renderApp(EDITOR, client([group()], { catalog: { deleteModifierOption } }));

  fireEvent.click(
    await screen.findByRole('button', { name: 'Delete Chutney' }),
  );
  expect(
    screen.getByText(/last available choice in its group/i),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Delete choice' }));

  await waitFor(() => {
    expect(deleteModifierOption).toHaveBeenCalledWith(
      SHALIK,
      'o1',
      'csrf-token-1',
    );
  });
});

test('staff hold no modifier authority of any kind', async () => {
  renderApp(EDITOR, client([group()], {}, 'staff'));

  // They can read the tree...
  expect(
    await screen.findByRole('heading', { name: 'Choose a side' }),
  ).toBeInTheDocument();
  expect(screen.getByText('Chutney')).toBeInTheDocument();
  // ...but every write affordance is absent.
  expect(screen.queryByRole('button', { name: 'New group' })).toBeNull();
  expect(
    screen.queryByRole('button', { name: 'Edit group Choose a side' }),
  ).toBeNull();
  expect(screen.queryByRole('button', { name: 'Delete Chutney' })).toBeNull();
  expect(screen.queryByRole('button', { name: /Add a choice/ })).toBeNull();
});
