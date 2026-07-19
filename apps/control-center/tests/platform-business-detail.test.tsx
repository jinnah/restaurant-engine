import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import type { ApiResult, BusinessSummary } from '@restaurant-engine/api-client';
import {
  adminSessionView,
  apiError,
  business,
  envelope,
  makeClient,
  ok,
} from './support/mockClient';
import { renderApp } from './support/render';

const BIZ_ID = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const DETAIL_PATH = `/platform/businesses/${BIZ_ID}`;

function adminClient(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
    ...overrides,
    platform: {
      // The invitations panel loads on every detail render; default it
      // to an empty page so lifecycle tests stay single-concern.
      listInvitations: vi.fn(async () =>
        ok({ items: [], total: 0, limit: 10, offset: 0 }),
      ),
      ...overrides.platform,
    },
  });
}

test('the detail page renders the business facts and provisioning action', async () => {
  const getBusiness = vi.fn(async () => ok(business()));
  renderApp(DETAIL_PATH, adminClient({ platform: { getBusiness } }));

  expect(
    await screen.findByRole('heading', { name: /shalik/i }),
  ).toBeInTheDocument();
  expect(screen.getByText('USD')).toBeInTheDocument();
  expect(screen.getByText('America/New_York')).toBeInTheDocument();
  expect(
    screen.getByRole('button', { name: /^activate$/i }),
  ).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /suspend/i })).toBeNull();
});

test('activation confirms in a dialog, sends CSRF, and updates the status', async () => {
  const getBusiness = vi.fn(async () => ok(business()));
  const activate = vi.fn(async () => ok(business({ status: 'active' })));
  renderApp(DETAIL_PATH, adminClient({ platform: { getBusiness, activate } }));

  fireEvent.click(await screen.findByRole('button', { name: /^activate$/i }));
  const dialog = await screen.findByRole('dialog', {
    name: /activate this business/i,
  });
  expect(dialog).toHaveTextContent(/at least one owner/i);
  // Focus moved into the dialog.
  expect(dialog.contains(document.activeElement)).toBe(true);

  fireEvent.click(within(dialog).getByRole('button', { name: /^activate$/i }));
  await waitFor(() => {
    expect(activate).toHaveBeenCalledWith(BIZ_ID, 'csrf-token-1');
  });
  expect(await screen.findByText('active')).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).toBeNull();
});

test('an activation 409 shows the honest server message', async () => {
  const getBusiness = vi.fn(async () => ok(business()));
  const activate = vi.fn(async () =>
    apiError(
      409,
      envelope(
        'invalid_state',
        'An active business requires at least one owner membership.',
      ),
    ),
  );
  renderApp(DETAIL_PATH, adminClient({ platform: { getBusiness, activate } }));

  fireEvent.click(await screen.findByRole('button', { name: /^activate$/i }));
  fireEvent.click(
    within(await screen.findByRole('dialog')).getByRole('button', {
      name: /^activate$/i,
    }),
  );

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/requires at least one owner/i);
  expect(alert).toHaveFocus();
  expect(screen.queryByRole('dialog')).toBeNull();
});

test('closing requires typing the business name', async () => {
  const getBusiness = vi.fn(async () => ok(business({ status: 'suspended' })));
  const close = vi.fn(async () => ok(business({ status: 'closed' })));
  renderApp(DETAIL_PATH, adminClient({ platform: { getBusiness, close } }));

  fireEvent.click(await screen.findByRole('button', { name: /^close$/i }));
  const dialog = await screen.findByRole('dialog', {
    name: /close this business permanently/i,
  });
  const confirm = within(dialog).getByRole('button', {
    name: /close permanently/i,
  });
  expect(confirm).toBeDisabled();

  fireEvent.change(within(dialog).getByLabelText(/type/i), {
    target: { value: 'Shalik' },
  });
  expect(confirm).toBeEnabled();
  fireEvent.click(confirm);
  await waitFor(() => {
    expect(close).toHaveBeenCalledWith(BIZ_ID, 'csrf-token-1');
  });
  expect(await screen.findByText('closed')).toBeInTheDocument();
  expect(screen.getByText(/closure is terminal/i)).toBeInTheDocument();
});

test('Escape cancels the dialog and returns focus to the trigger', async () => {
  const getBusiness = vi.fn(async () => ok(business()));
  renderApp(DETAIL_PATH, adminClient({ platform: { getBusiness } }));

  const trigger = await screen.findByRole('button', { name: /^activate$/i });
  trigger.focus(); // jsdom does not focus on click; a real browser does.
  fireEvent.click(trigger);
  const dialog = await screen.findByRole('dialog');
  fireEvent.keyDown(dialog, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).toBeNull();
  await waitFor(() => {
    expect(trigger).toHaveFocus();
  });
});

test('the confirm action cannot be double-submitted while pending', async () => {
  const getBusiness = vi.fn(async () => ok(business()));
  let release: () => void = () => {};
  const activate = vi.fn(
    () =>
      new Promise<ApiResult<BusinessSummary>>((resolve) => {
        release = () => {
          resolve(ok(business({ status: 'active' })));
        };
      }),
  );
  renderApp(DETAIL_PATH, adminClient({ platform: { getBusiness, activate } }));

  fireEvent.click(await screen.findByRole('button', { name: /^activate$/i }));
  const dialog = await screen.findByRole('dialog');
  const confirm = within(dialog).getByRole('button', { name: /^activate$/i });
  fireEvent.click(confirm);

  const working = await within(dialog).findByRole('button', {
    name: /working/i,
  });
  expect(working).toBeDisabled();
  fireEvent.click(working);
  release();
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  expect(activate).toHaveBeenCalledTimes(1);
});

test('a failed business load offers retry and a way back', async () => {
  const getBusiness = vi
    .fn()
    .mockResolvedValueOnce(apiError(404, envelope('not_found', 'Not found.')))
    .mockResolvedValueOnce(ok(business()));
  renderApp(DETAIL_PATH, adminClient({ platform: { getBusiness } }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/could not be loaded/i);
  expect(
    screen.getByRole('link', { name: /back to businesses/i }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /try again/i }));
  expect(
    await screen.findByRole('heading', { name: /shalik/i }),
  ).toBeInTheDocument();
});
