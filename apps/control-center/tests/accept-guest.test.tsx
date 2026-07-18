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
  ok,
} from './support/mockClient';
import { renderApp } from './support/render';

const RAW_TOKEN = 'raw-invitation-token-value-123';
const FULL_EMAIL = 'invitee@example.com';
const ACCEPT_PATH = '/invitations/accept';

function previewResponse(): InvitationPreviewResponse {
  return {
    business_name: 'Shalik',
    role: 'staff',
    email_hint: 'i***@example.com',
  };
}

function acceptedResponse(): InvitationAcceptedResponse {
  return {
    status: 'accepted',
    business_id: '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001',
    email: FULL_EMAIL,
    role: 'staff',
  };
}

async function pasteTokenAndContinue() {
  fireEvent.change(await screen.findByLabelText(/invitation token/i), {
    target: { value: RAW_TOKEN },
  });
  fireEvent.click(screen.getByRole('button', { name: /continue/i }));
}

test('session loading renders neither acceptance form', () => {
  const pendingForever = new Promise<never>(() => {
    /* never resolves */
  });
  renderApp(
    ACCEPT_PATH,
    makeClient({ auth: { getSession: vi.fn(() => pendingForever) } }),
  );
  expect(screen.getByRole('status')).toHaveTextContent(
    /checking your session/i,
  );
  expect(screen.queryByLabelText(/invitation token/i)).toBeNull();
  expect(screen.queryByLabelText(/your name/i)).toBeNull();
});

test('guest preview shows only the approved fields, then acceptance succeeds without login', async () => {
  const preview = vi.fn(async () => ok(previewResponse()));
  const accept = vi.fn(async () => ok(acceptedResponse(), 201));
  const getSession = vi.fn(async () => apiError(401, null));
  const client = makeClient({
    auth: { getSession },
    invitations: { preview, accept },
  });
  const { router, queryClient } = renderApp(ACCEPT_PATH, client);

  await pasteTokenAndContinue();

  // Approved preview fields only; the full invited email never renders.
  expect(await screen.findByText('Shalik')).toBeInTheDocument();
  expect(screen.getByText('staff')).toBeInTheDocument();
  expect(screen.getByText('i***@example.com')).toBeInTheDocument();
  expect(preview).toHaveBeenCalledExactlyOnceWith({ token: RAW_TOKEN });

  fireEvent.change(screen.getByLabelText(/your name/i), {
    target: { value: 'New Member' },
  });
  fireEvent.change(screen.getByLabelText(/^password$/i), {
    target: { value: 'a brand new pw for tests!' },
  });
  fireEvent.change(screen.getByLabelText(/confirm password/i), {
    target: { value: 'a brand new pw for tests!' },
  });
  fireEvent.click(screen.getByRole('button', { name: /accept invitation/i }));

  const success = await screen.findByRole('status');
  expect(success).toHaveTextContent(/invitation accepted/i);
  expect(success).toHaveTextContent(/not.*signed\s*in/i);
  expect(screen.getByRole('link', { name: /go to sign in/i })).toHaveAttribute(
    'href',
    '/login',
  );
  expect(accept).toHaveBeenCalledExactlyOnceWith({
    token: RAW_TOKEN,
    display_name: 'New Member',
    password: 'a brand new pw for tests!',
  });

  // No auto-login: the session was never re-fetched or written.
  expect(getSession).toHaveBeenCalledTimes(1);

  // Token hygiene: not in the URL, storage, DOM, or any query key.
  expect(router.state.location.pathname).toBe(ACCEPT_PATH);
  expect(router.state.location.search).toBe('');
  expect(document.body.innerHTML).not.toContain(RAW_TOKEN);
  expect(document.body.innerHTML).not.toContain(FULL_EMAIL);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
  const cachedKeys = JSON.stringify(
    queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey),
  );
  expect(cachedKeys).not.toContain(RAW_TOKEN);
});

test('an invalid token renders the neutral message without a cause', async () => {
  renderApp(ACCEPT_PATH, makeClient()); // default preview: neutral 404

  await pasteTokenAndContinue();

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(INVALID_INVITATION);
  expect(alert.textContent).not.toMatch(/expired only|revoked|accepted by/i);
});

test('password confirmation mismatch is blocked locally', async () => {
  const preview = vi.fn(async () => ok(previewResponse()));
  const accept = vi.fn();
  const client = makeClient({ invitations: { preview, accept } });
  renderApp(ACCEPT_PATH, client);

  await pasteTokenAndContinue();
  fireEvent.change(await screen.findByLabelText(/your name/i), {
    target: { value: 'New Member' },
  });
  fireEvent.change(screen.getByLabelText(/^password$/i), {
    target: { value: 'first password 111!' },
  });
  fireEvent.change(screen.getByLabelText(/confirm password/i), {
    target: { value: 'second password 222!' },
  });
  fireEvent.click(screen.getByRole('button', { name: /accept invitation/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /passwords do not match/i,
  );
  expect(accept).not.toHaveBeenCalled();
});

test('422 field errors on acceptance map inline', async () => {
  const preview = vi.fn(async () => ok(previewResponse()));
  const accept = vi.fn(async () =>
    apiError(
      422,
      envelope('validation_error', 'Validation failed.', [
        {
          field: 'body.password',
          code: 'string_too_short',
          message: 'Password must be at least 12 characters.',
        },
      ]),
    ),
  );
  renderApp(ACCEPT_PATH, makeClient({ invitations: { preview, accept } }));

  await pasteTokenAndContinue();
  fireEvent.change(await screen.findByLabelText(/your name/i), {
    target: { value: 'New Member' },
  });
  fireEvent.change(screen.getByLabelText(/^password$/i), {
    target: { value: 'short' },
  });
  fireEvent.change(screen.getByLabelText(/confirm password/i), {
    target: { value: 'short' },
  });
  fireEvent.click(screen.getByRole('button', { name: /accept invitation/i }));

  const passwordInput = await screen.findByLabelText(/^password$/i);
  await waitFor(() => {
    expect(passwordInput).toHaveAttribute('aria-invalid', 'true');
  });
  expect(passwordInput).toHaveAccessibleDescription(
    'Password must be at least 12 characters.',
  );
});

test('the token input suppresses browser assistance', async () => {
  renderApp(ACCEPT_PATH, makeClient());
  const input = await screen.findByLabelText(/invitation token/i);
  expect(input).toHaveAttribute('autocomplete', 'off');
  expect(input).toHaveAttribute('spellcheck', 'false');
  expect(input).toHaveAttribute('autocorrect', 'off');
  expect(input).toHaveAttribute('autocapitalize', 'off');
});
