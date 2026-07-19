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
