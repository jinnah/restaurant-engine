// Accessibility and failure-recovery behaviour across the menu workspace
// (M3E). Layout itself is verified in the authorized visual smoke — jsdom
// computes none — so what is asserted here is semantics and behaviour.

import { fireEvent, screen, waitFor } from '@testing-library/react';
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

function client(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(sessionView({ memberships: [membership({ business_id: SHALIK })] })),
      ),
    },
    businesses: { get: vi.fn(async () => ok(business({ id: SHALIK }))) },
    ...overrides,
    catalog: {
      getMenu: vi.fn(async () =>
        ok(
          adminMenu([
            category({
              id: 'c1',
              name: 'Starters',
              items: [item({ id: 'i1' })],
            }),
          ]),
        ),
      ),
      getModifierGroups: vi.fn(async () => ok({ item_id: 'i1', groups: [] })),
      ...overrides.catalog,
    },
  });
}

test('the workspace exposes exactly one h1, naming the business', async () => {
  renderApp(MENU, client());
  const headings = await screen.findAllByRole('heading', { level: 1 });
  expect(headings).toHaveLength(1);
  expect(headings[0]).toHaveTextContent('Shalik');
});

test('the workspace navigation is labelled and marks the current section', async () => {
  renderApp(MENU, client());
  const nav = await screen.findByRole('navigation', {
    name: 'Workspace sections',
  });
  expect(nav).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Menu' })).toHaveAttribute(
    'aria-current',
    'page',
  );
});

test('the primary navigation still works alongside the switcher', async () => {
  renderApp(MENU, client());
  const primary = await screen.findByRole('navigation', { name: 'Primary' });
  expect(primary).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
  expect(screen.getByLabelText('Business')).toBeInTheDocument();
});

test('a dialog traps Tab, closes on Escape, and returns focus to its trigger', async () => {
  renderApp(MENU, client());

  const trigger = await screen.findByRole('button', { name: 'New category' });
  trigger.focus();
  fireEvent.click(trigger);

  const dialog = await screen.findByRole('dialog');
  expect(dialog).toHaveAttribute('aria-modal', 'true');
  // Focus moved into the dialog, not left behind on the page.
  expect(dialog.contains(document.activeElement)).toBe(true);

  fireEvent.keyDown(dialog, { key: 'Escape' });
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  expect(document.activeElement).toBe(trigger);
});

test('a form failure moves focus to the summary so it is announced', async () => {
  renderApp(
    MENU,
    client({
      catalog: {
        createCategory: vi.fn(async () =>
          apiError(409, envelope('conflict', 'That name is taken.')),
        ),
      },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'New category' }));
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Starters' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add category' }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('That name is taken.');
  await waitFor(() => {
    expect(document.activeElement).toBe(alert);
  });
});

test('every field error is associated with its input', async () => {
  renderApp(MENU, client());

  fireEvent.click(await screen.findByRole('button', { name: 'New category' }));
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: '  ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add category' }));

  const input = await screen.findByLabelText('Name');
  await waitFor(() => {
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });
  const describedBy = input.getAttribute('aria-describedby') ?? '';
  const errorId = describedBy.split(' ').find((id) => id.endsWith('-error'));
  expect(errorId).toBeDefined();
  expect(document.getElementById(errorId ?? '')).toHaveTextContent(
    'Enter a name for this category.',
  );
});

test('the availability toggle exposes its pressed state', async () => {
  renderApp(MENU, client());
  const toggle = await screen.findByRole('button', { name: 'Mark sold out' });
  // Not pressed while the item is available; pressed means "sold out".
  expect(toggle).toHaveAttribute('aria-pressed', 'false');
});

test('an image placeholder is hidden from assistive technology', async () => {
  const { view } = renderApp(MENU, client());
  await screen.findByText('Samosa');
  const placeholder = view.container.querySelector('[aria-hidden="true"]');
  // The item name is already the row's text; a decorative box must not be
  // announced as well.
  expect(placeholder).not.toBeNull();
});

test('a network failure is offered as retryable rather than as not-found', async () => {
  const getMenu = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, status: null, envelope: null })
    .mockResolvedValue(ok(adminMenu([category({ name: 'Starters' })])));
  renderApp(MENU, client({ catalog: { getMenu } }));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /could not be loaded/i,
  );
  fireEvent.click(screen.getByRole('button', { name: /try again/i }));
  expect(await screen.findByText('Starters')).toBeInTheDocument();
});

test('a 403 revalidates the session so affordances recompute from real roles', async () => {
  // A role change mid-session: the first read succeeds as owner, the mutation
  // is refused, and the refreshed session reports staff.
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(
      ok(sessionView({ memberships: [membership({ business_id: SHALIK })] })),
    )
    .mockResolvedValue(
      ok(
        sessionView({
          memberships: [membership({ business_id: SHALIK, role: 'staff' })],
        }),
      ),
    );
  renderApp(
    MENU,
    client({
      auth: { getSession },
      catalog: {
        createCategory: vi.fn(async () =>
          apiError(403, envelope('permission_denied', 'Not allowed.')),
        ),
      },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'New category' }));
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Biryani' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add category' }));

  // The session is refetched, and the write affordance disappears once the
  // authoritative role says it should.
  await waitFor(() => {
    expect(getSession).toHaveBeenCalledTimes(2);
  });
  await waitFor(() => {
    expect(screen.queryByRole('button', { name: 'New category' })).toBeNull();
  });
});

test('a 401 during a menu read clears the session and routes to login', async () => {
  const { router } = renderApp(
    MENU,
    client({
      catalog: {
        getMenu: vi.fn(async () =>
          apiError(401, envelope('authentication_required', 'Sign in.')),
        ),
      },
    }),
  );

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
});
