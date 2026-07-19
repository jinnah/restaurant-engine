import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import {
  INVALID_RESET,
  apiError,
  envelope,
  makeClient,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

const RAW_TOKEN = 'raw-reset-token-789';
const RESET_PATH = '/password-reset';
const NEW_PASSWORD = 'an entirely new pw 42!';

async function fillForm(confirmValue = NEW_PASSWORD) {
  fireEvent.change(await screen.findByLabelText(/reset token/i), {
    target: { value: RAW_TOKEN },
  });
  fireEvent.change(screen.getByLabelText(/^new password$/i), {
    target: { value: NEW_PASSWORD },
  });
  fireEvent.change(screen.getByLabelText(/confirm new password/i), {
    target: { value: confirmValue },
  });
  fireEvent.click(screen.getByRole('button', { name: /change password/i }));
}

test('successful redemption clears sensitive state and never implies login', async () => {
  const redeem = vi.fn(async () => ok({ status: 'password_reset' as const }));
  const client = makeClient({ passwordResets: { redeem } });
  const { router, queryClient } = renderApp(RESET_PATH, client);

  await fillForm();

  const success = await screen.findByRole('status');
  expect(success).toHaveTextContent(/password changed/i);
  expect(success).toHaveTextContent(/not.*signed\s*in/i);
  expect(screen.getByRole('link', { name: /go to sign in/i })).toHaveAttribute(
    'href',
    '/login',
  );
  expect(redeem).toHaveBeenCalledExactlyOnceWith({
    token: RAW_TOKEN,
    new_password: NEW_PASSWORD,
  });

  // Sensitive values are gone from DOM, URL, storage, and query keys.
  expect(document.body.innerHTML).not.toContain(RAW_TOKEN);
  expect(document.body.innerHTML).not.toContain(NEW_PASSWORD);
  expect(router.state.location.search).toBe('');
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

test('confirmation mismatch is blocked locally', async () => {
  const redeem = vi.fn();
  renderApp(RESET_PATH, makeClient({ passwordResets: { redeem } }));

  await fillForm('a different password 43!');

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /passwords do not match/i,
  );
  expect(redeem).not.toHaveBeenCalled();
});

test('an invalid token renders the neutral message', async () => {
  renderApp(RESET_PATH, makeClient()); // default redeem: neutral 404

  await fillForm();

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(INVALID_RESET);
});

test('422 field errors map inline to the new-password input', async () => {
  const redeem = vi.fn(async () =>
    apiError(
      422,
      envelope('validation_error', 'Validation failed.', [
        {
          field: 'body.new_password',
          code: 'string_too_short',
          message: 'Password must be at least 12 characters.',
        },
      ]),
    ),
  );
  renderApp(RESET_PATH, makeClient({ passwordResets: { redeem } }));

  await fillForm();

  const input = await screen.findByLabelText(/^new password$/i);
  await waitFor(() => {
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });
  expect(input).toHaveAccessibleDescription(
    'Password must be at least 12 characters.',
  );
});

test('reset while authenticated clears the cached session immediately', async () => {
  const redeem = vi.fn(async () => ok({ status: 'password_reset' as const }));
  const getSession = vi.fn(async () => ok(sessionView()));
  const client = makeClient({
    auth: { getSession },
    passwordResets: { redeem },
  });

  // Start as a genuinely authenticated tab, then visit the reset page.
  const { router, queryClient } = renderApp('/', client);
  expect(await screen.findByText(/signed in as/i)).toBeInTheDocument();
  await router.navigate(RESET_PATH);

  // The public form renders even though a session exists — the contract
  // never switches to an authenticated mutation.
  expect(await screen.findByLabelText(/reset token/i)).toBeInTheDocument();

  await fillForm();
  await screen.findByRole('status');

  // Cached authenticated state is gone, with no refetch of the dead
  // session (bootstrap was the only fetch), and no authenticated chrome.
  expect(queryClient.getQueryData(['session'])).toEqual({ kind: 'anonymous' });
  expect(getSession).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(/signed in as/i)).toBeNull();
});
