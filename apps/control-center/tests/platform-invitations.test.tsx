import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { vi, expect, test, afterEach } from 'vitest';
import type {
  ApiClient,
  InvitationSummary,
} from '@restaurant-engine/api-client';
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

function invitation(
  overrides: Partial<InvitationSummary> = {},
): InvitationSummary {
  return {
    invitation_id: 'c9d8e7f6-5a4b-3c2d-1e0f-9a8b7c6d5e4f',
    email: 'newowner@example.com',
    role: 'owner',
    state: 'pending',
    created_at: '2026-07-19T00:00:00Z',
    expires_at: '2026-07-26T00:00:00Z',
    invited_by_user_id: '9c1e5b7a-3d2f-4a6b-8c0d-1e2f3a4b5c6d',
    ...overrides,
  };
}

function invitationPage(items: InvitationSummary[], total = items.length) {
  return ok({ items, total, limit: 10, offset: 0 });
}

function issued(token: string) {
  return ok(
    {
      invitation_id: 'c9d8e7f6-5a4b-3c2d-1e0f-9a8b7c6d5e4f',
      email: 'newowner@example.com',
      role: 'owner' as const,
      token,
      expires_at: '2026-07-26T00:00:00Z',
    },
    201,
  );
}

function detailClient(platform: Partial<ApiClient['platform']> = {}) {
  return makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
    platform: {
      getBusiness: vi.fn(async () => ok(business())),
      listInvitations: vi.fn(async () => invitationPage([])),
      ...platform,
    },
  });
}

const clipboardWrite = vi.fn(async () => {});

function stubClipboard() {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: clipboardWrite },
    configurable: true,
  });
}

afterEach(() => {
  clipboardWrite.mockClear();
});

test('issuing an invitation reveals the one-time token with a copy action', async () => {
  stubClipboard();
  const createInvitation = vi.fn(async () => issued('raw-token-abc123'));
  const listInvitations = vi
    .fn()
    .mockResolvedValueOnce(invitationPage([]))
    .mockResolvedValue(invitationPage([invitation()]));
  renderApp(DETAIL_PATH, detailClient({ createInvitation, listInvitations }));

  fireEvent.change(await screen.findByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.change(screen.getByLabelText(/^role$/i), {
    target: { value: 'owner' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));

  const reveal = await screen.findByText('raw-token-abc123');
  expect(reveal).toBeInTheDocument();
  expect(screen.getByText(/shown once/i)).toBeInTheDocument();
  expect(createInvitation).toHaveBeenCalledWith(
    BIZ_ID,
    { email: 'newowner@example.com', role: 'owner' },
    'csrf-token-1',
  );

  fireEvent.click(screen.getByRole('button', { name: /copy token/i }));
  await waitFor(() => {
    expect(clipboardWrite).toHaveBeenCalledWith('raw-token-abc123');
  });
  expect(
    await screen.findByRole('button', { name: /^copied$/i }),
  ).toBeInTheDocument();

  // The pending list refreshed.
  expect(
    await screen.findByRole('button', {
      name: /revoke invitation for newowner@example.com/i,
    }),
  ).toBeInTheDocument();
});

test('dismissing the reveal removes the token from the document', async () => {
  const createInvitation = vi.fn(async () => issued('raw-token-dismiss'));
  renderApp(DETAIL_PATH, detailClient({ createInvitation }));

  fireEvent.change(await screen.findByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));
  await screen.findByText('raw-token-dismiss');

  fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
  expect(screen.queryByText('raw-token-dismiss')).toBeNull();
});

test('a new issuance attempt discards the previous token immediately', async () => {
  const createInvitation = vi
    .fn()
    .mockResolvedValueOnce(issued('first-token'))
    .mockResolvedValueOnce(issued('second-token'));
  renderApp(DETAIL_PATH, detailClient({ createInvitation }));

  fireEvent.change(await screen.findByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));
  await screen.findByText('first-token');

  fireEvent.change(screen.getByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));
  await screen.findByText('second-token');
  expect(screen.queryByText('first-token')).toBeNull();
});

test('revoking asks for confirmation and refreshes the list', async () => {
  const revokeInvitation = vi.fn(async () =>
    ok({ status: 'revoked' as const }),
  );
  const listInvitations = vi
    .fn()
    .mockResolvedValueOnce(invitationPage([invitation()]))
    .mockResolvedValue(invitationPage([]));
  renderApp(DETAIL_PATH, detailClient({ revokeInvitation, listInvitations }));

  fireEvent.click(
    await screen.findByRole('button', {
      name: /revoke invitation for newowner@example.com/i,
    }),
  );
  const dialog = await screen.findByRole('dialog', {
    name: /revoke the invitation/i,
  });
  fireEvent.click(within(dialog).getByRole('button', { name: /^revoke$/i }));

  await waitFor(() => {
    expect(revokeInvitation).toHaveBeenCalledWith(
      BIZ_ID,
      invitation().invitation_id,
      'csrf-token-1',
    );
  });
  expect(
    await screen.findByText(/no pending invitations/i),
  ).toBeInTheDocument();
});

test('a 409 (already invited) surfaces the honest message', async () => {
  const createInvitation = vi.fn(async () =>
    apiError(
      409,
      envelope('conflict', 'A live invitation already exists for this email.'),
    ),
  );
  renderApp(DETAIL_PATH, detailClient({ createInvitation }));

  fireEvent.change(await screen.findByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/already exists/i);
  expect(alert).toHaveFocus();
});

test('a suspended business offers revocation but not issuance', async () => {
  const getBusiness = vi.fn(async () => ok(business({ status: 'suspended' })));
  const listInvitations = vi.fn(async () => invitationPage([invitation()]));
  renderApp(DETAIL_PATH, detailClient({ getBusiness, listInvitations }));

  expect(
    await screen.findByText(/issued only while the business is provisioning/i),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText(/^email$/i)).toBeNull();
  expect(
    await screen.findByRole('button', {
      name: /revoke invitation for newowner@example.com/i,
    }),
  ).toBeInTheDocument();
});

test('the raw token never enters any query or mutation cache (F2)', async () => {
  const createInvitation = vi.fn(async () => issued('raw-token-cache-check'));
  const { queryClient } = renderApp(
    DETAIL_PATH,
    detailClient({ createInvitation }),
  );

  fireEvent.change(await screen.findByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));
  await screen.findByText('raw-token-cache-check');

  // The reveal renders from component state only: neither the query
  // cache nor the token-bearing mutation state retains the raw token.
  const cacheDump = JSON.stringify({
    queries: queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.state.data ?? null),
    mutations: queryClient
      .getMutationCache()
      .getAll()
      .map((mutation) => mutation.state),
  });
  expect(cacheDump).not.toContain('raw-token-cache-check');
});

test('a session clear plus remount cannot recover an issued token (F2)', async () => {
  const createInvitation = vi.fn(async () => issued('raw-token-remount'));
  const { queryClient, view } = renderApp(
    DETAIL_PATH,
    detailClient({ createInvitation }),
  );

  fireEvent.change(await screen.findByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));
  await screen.findByText('raw-token-remount');

  view.unmount();
  expect(screen.queryByText('raw-token-remount')).toBeNull();
  const cacheDump = JSON.stringify({
    queries: queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.state.data ?? null),
    mutations: queryClient
      .getMutationCache()
      .getAll()
      .map((mutation) => mutation.state),
  });
  expect(cacheDump).not.toContain('raw-token-remount');
});

test('a failed later attempt does not resurrect an earlier token (F2)', async () => {
  const createInvitation = vi
    .fn()
    .mockResolvedValueOnce(issued('raw-token-first-success'))
    .mockResolvedValueOnce(
      apiError(409, envelope('conflict', 'A live invitation already exists.')),
    );
  const { queryClient } = renderApp(
    DETAIL_PATH,
    detailClient({ createInvitation }),
  );

  fireEvent.change(await screen.findByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));
  await screen.findByText('raw-token-first-success');

  fireEvent.change(screen.getByLabelText(/^email$/i), {
    target: { value: 'newowner@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue invitation/i }));
  await screen.findByRole('alert');
  expect(screen.queryByText('raw-token-first-success')).toBeNull();
  const cacheDump = JSON.stringify(
    queryClient
      .getMutationCache()
      .getAll()
      .map((mutation) => mutation.state),
  );
  expect(cacheDump).not.toContain('raw-token-first-success');
});

test('an emptied later page steps back instead of claiming emptiness (F3)', async () => {
  const items = Array.from({ length: 10 }, (_, index) =>
    invitation({
      invitation_id: '00000000-0000-4000-8000-00000000000' + String(index),
      email: 'pending' + String(index) + '@example.com',
    }),
  );
  const listInvitations = vi
    .fn()
    // Page one: full page of a shrinking 11-item list.
    .mockResolvedValueOnce(ok({ items, total: 11, limit: 10, offset: 0 }))
    // Page two: the list shrank to 3 while navigating — page empty.
    .mockResolvedValueOnce(ok({ items: [], total: 3, limit: 10, offset: 10 }))
    // The step-back lands on the first (and only) valid page.
    .mockResolvedValue(
      ok({ items: items.slice(0, 3), total: 3, limit: 10, offset: 0 }),
    );
  renderApp(DETAIL_PATH, detailClient({ listInvitations }));

  await screen.findByText('pending0@example.com');
  fireEvent.click(screen.getByRole('button', { name: /^next$/i }));

  // Never the misleading empty message; the valid page renders.
  await screen.findByText('pending2@example.com');
  expect(screen.queryByText(/no pending invitations/i)).toBeNull();
  expect(listInvitations).toHaveBeenLastCalledWith(BIZ_ID, {
    limit: 10,
    offset: 0,
  });
});

test('an offset beyond several vanished pages settles without looping (F3)', async () => {
  const items = Array.from({ length: 10 }, (_, index) =>
    invitation({
      invitation_id: '00000000-0000-4000-8000-0000000000' + String(10 + index),
      email: 'bulk' + String(index) + '@example.com',
    }),
  );
  const listInvitations = vi
    .fn()
    .mockResolvedValueOnce(ok({ items, total: 21, limit: 10, offset: 0 }))
    .mockResolvedValueOnce(ok({ items, total: 21, limit: 10, offset: 10 }))
    // Everything vanished while on page three.
    .mockResolvedValueOnce(ok({ items: [], total: 0, limit: 10, offset: 20 }))
    .mockResolvedValueOnce(ok({ items: [], total: 0, limit: 10, offset: 10 }))
    .mockResolvedValue(ok({ items: [], total: 0, limit: 10, offset: 0 }));
  renderApp(DETAIL_PATH, detailClient({ listInvitations }));

  await screen.findByText('bulk0@example.com');
  fireEvent.click(screen.getByRole('button', { name: /^next$/i }));
  // Wait for page two to render (the pager unmounts while loading).
  const nextAgain = await screen.findByRole('button', { name: /^next$/i });
  await waitFor(() => {
    expect(listInvitations).toHaveBeenLastCalledWith(BIZ_ID, {
      limit: 10,
      offset: 10,
    });
  });
  fireEvent.click(nextAgain);

  // Settles on offset 0 and only then shows the honest empty state.
  expect(
    await screen.findByText(/no pending invitations/i),
  ).toBeInTheDocument();
  expect(listInvitations).toHaveBeenLastCalledWith(BIZ_ID, {
    limit: 10,
    offset: 0,
  });
  const settledCalls = listInvitations.mock.calls.length;
  await new Promise((resolve) => setTimeout(resolve, 150));
  expect(listInvitations.mock.calls.length).toBe(settledCalls); // no loop
});

test('revoking the last item of a later page returns to the previous page (F3)', async () => {
  const items = Array.from({ length: 10 }, (_, index) =>
    invitation({
      invitation_id: '00000000-0000-4000-8000-0000000000' + String(30 + index),
      email: 'page1-' + String(index) + '@example.com',
    }),
  );
  const last = invitation({
    invitation_id: '00000000-0000-4000-8000-000000000099',
    email: 'lastone@example.com',
  });
  const revokeInvitation = vi.fn(async () =>
    ok({ status: 'revoked' as const }),
  );
  const listInvitations = vi
    .fn()
    .mockResolvedValueOnce(ok({ items, total: 11, limit: 10, offset: 0 }))
    .mockResolvedValueOnce(
      ok({ items: [last], total: 11, limit: 10, offset: 10 }),
    )
    // After the revoke, page two is empty but ten records remain.
    .mockResolvedValueOnce(ok({ items: [], total: 10, limit: 10, offset: 10 }))
    .mockResolvedValue(ok({ items, total: 10, limit: 10, offset: 0 }));
  renderApp(DETAIL_PATH, detailClient({ revokeInvitation, listInvitations }));

  await screen.findByText('page1-0@example.com');
  fireEvent.click(screen.getByRole('button', { name: /^next$/i }));
  fireEvent.click(
    await screen.findByRole('button', {
      name: /revoke invitation for lastone@example.com/i,
    }),
  );
  fireEvent.click(
    within(await screen.findByRole('dialog')).getByRole('button', {
      name: /^revoke$/i,
    }),
  );

  // Lands back on the previous page with Previous/Next semantics intact.
  expect(await screen.findByText('page1-0@example.com')).toBeInTheDocument();
  expect(screen.queryByText(/no pending invitations/i)).toBeNull();
  expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
  expect(listInvitations).toHaveBeenLastCalledWith(BIZ_ID, {
    limit: 10,
    offset: 0,
  });
});
