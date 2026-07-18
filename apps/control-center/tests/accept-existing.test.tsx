import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import type {
  InvitationAcceptedResponse,
  InvitationPreviewResponse,
} from '@restaurant-engine/api-client';
import {
  INVALID_INVITATION,
  apiError,
  envelope,
  makeClient,
  membership,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

const RAW_TOKEN = 'raw-existing-invitation-token-456';
const ACCEPT_PATH = '/invitations/accept';
const NEW_BUSINESS_ID = '7a1c2d3e-0f00-4b1a-8c2d-3e4f5a6b7c8d';

function previewResponse(): InvitationPreviewResponse {
  return {
    business_name: 'Juniper',
    role: 'staff',
    email_hint: 'o***@example.com',
  };
}

function acceptedResponse(): InvitationAcceptedResponse {
  return {
    status: 'accepted',
    business_id: NEW_BUSINESS_ID,
    email: 'owner@example.com',
    role: 'staff',
  };
}

function refreshedView() {
  return sessionView({
    memberships: [
      membership(),
      membership({
        business_id: NEW_BUSINESS_ID,
        business_slug: 'juniper',
        business_name: 'Juniper',
        role: 'staff',
        business_status: 'active',
      }),
    ],
  });
}

async function previewAndConfirm() {
  fireEvent.change(await screen.findByLabelText(/invitation token/i), {
    target: { value: RAW_TOKEN },
  });
  fireEvent.click(screen.getByRole('button', { name: /continue/i }));
  fireEvent.click(
    await screen.findByRole('button', { name: /accept invitation/i }),
  );
}

test('an authenticated user sees the existing-user flow, never account fields', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
    invitations: { preview: vi.fn(async () => ok(previewResponse())) },
  });
  renderApp(ACCEPT_PATH, client);

  expect(
    await screen.findByText(/signed in as/i, { exact: false }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/invitation token/i), {
    target: { value: RAW_TOKEN },
  });
  fireEvent.click(screen.getByRole('button', { name: /continue/i }));

  // Confirmation shows the approved preview and asks for explicit consent.
  expect(
    await screen.findByRole('heading', { name: /join this business/i }),
  ).toBeInTheDocument();
  expect(screen.getAllByText('Juniper').length).toBeGreaterThan(0);
  expect(screen.getByText('o***@example.com')).toBeInTheDocument();
  // Never display-name or password fields for an authenticated user.
  expect(screen.queryByLabelText(/your name/i)).toBeNull();
  expect(screen.queryByLabelText(/password/i)).toBeNull();
});

test('acceptance sends the current CSRF token, refreshes the session, and lands on /', async () => {
  const acceptExisting = vi.fn(async () => ok(acceptedResponse()));
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(ok(sessionView())) // bootstrap: one membership
    .mockResolvedValue(ok(refreshedView())); // authoritative refresh
  const client = makeClient({
    auth: { getSession },
    invitations: {
      preview: vi.fn(async () => ok(previewResponse())),
      acceptExisting,
    },
  });
  const { router, queryClient } = renderApp(ACCEPT_PATH, client);

  await previewAndConfirm();

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/');
  });
  expect(acceptExisting).toHaveBeenCalledExactlyOnceWith(
    { token: RAW_TOKEN },
    'csrf-token-1',
  );
  // The confirmed membership came from the refreshed authoritative session.
  expect(getSession.mock.calls.length).toBeGreaterThanOrEqual(2);
  expect(await screen.findByText('Juniper')).toBeInTheDocument();

  // Token hygiene after the terminal state.
  expect(document.body.innerHTML).not.toContain(RAW_TOKEN);
  const cachedKeys = JSON.stringify(
    queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey),
  );
  expect(cachedKeys).not.toContain(RAW_TOKEN);
});

test('refresh failure preserves acceptance and offers session retry only', async () => {
  const acceptExisting = vi.fn(async () => ok(acceptedResponse()));
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(ok(sessionView())) // bootstrap
    .mockResolvedValueOnce(apiError(503, null)) // refresh fails
    .mockResolvedValue(ok(refreshedView())); // retry succeeds
  const client = makeClient({
    auth: { getSession },
    invitations: {
      preview: vi.fn(async () => ok(previewResponse())),
      acceptExisting,
    },
  });
  const { router } = renderApp(ACCEPT_PATH, client);

  await previewAndConfirm();

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/accepted/i);
  expect(alert).toHaveTextContent(/could not refresh your session/i);
  // Terminal for the token: no token input, no acceptance button remains.
  expect(screen.queryByLabelText(/invitation token/i)).toBeNull();
  expect(
    screen.queryByRole('button', { name: /accept invitation/i }),
  ).toBeNull();

  fireEvent.click(
    screen.getByRole('button', { name: /retry loading session/i }),
  );
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/');
  });
  // The acceptance itself was never resubmitted.
  expect(acceptExisting).toHaveBeenCalledTimes(1);
});

test('a refreshed session missing the membership is a safe consistency state', async () => {
  const acceptExisting = vi.fn(async () => ok(acceptedResponse()));
  const getSession = vi.fn(async () => ok(sessionView())); // never gains it
  const client = makeClient({
    auth: { getSession },
    invitations: {
      preview: vi.fn(async () => ok(previewResponse())),
      acceptExisting,
    },
  });
  renderApp(ACCEPT_PATH, client);

  await previewAndConfirm();

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/has not appeared in your session yet/i);
  expect(
    screen.getByRole('button', { name: /refresh session/i }),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument();
  // No internal identifiers, no token, no resubmission path.
  expect(document.body.innerHTML).not.toContain(NEW_BUSINESS_ID);
  expect(document.body.innerHTML).not.toContain(RAW_TOKEN);
  expect(acceptExisting).toHaveBeenCalledTimes(1);
  expect(screen.queryByLabelText(/invitation token/i)).toBeNull();
});

test('a neutral 404 on authenticated acceptance reveals nothing', async () => {
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
    invitations: {
      preview: vi.fn(async () => ok(previewResponse())),
      // default acceptExisting: neutral 404
    },
  });
  renderApp(ACCEPT_PATH, client);

  await previewAndConfirm();

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(INVALID_INVITATION);
  expect(alert.textContent).not.toMatch(/email|expired only|revoked/i);
});

test('the honest already-member 409 maps safely', async () => {
  const acceptExisting = vi.fn(async () =>
    apiError(
      409,
      envelope('conflict', 'You are already a member of this business.'),
    ),
  );
  const client = makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
    invitations: {
      preview: vi.fn(async () => ok(previewResponse())),
      acceptExisting,
    },
  });
  renderApp(ACCEPT_PATH, client);

  await previewAndConfirm();

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'You are already a member of this business.',
  );
});
