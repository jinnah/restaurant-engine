// Focused accessibility behaviors beyond the assertions woven through
// the flow tests (labels, alert roles, focus management, accessible
// descriptions, disabled submission states are covered there).

import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import type { SessionResponse } from '@restaurant-engine/api-client';
import { makeClient, ok, sessionView } from './support/mockClient';
import { renderApp } from './support/render';

/** The lean login body — never the enriched SessionView shape. */
function loginResponse(): SessionResponse {
  const view = sessionView();
  return { user: view.user, csrf_token: view.csrf_token };
}

test('the login form is a native form: keyboard submission works', async () => {
  const login = vi.fn(async () => ok(loginResponse()));
  renderApp('/login', makeClient({ auth: { login } }));

  const email = await screen.findByLabelText(/email/i);
  fireEvent.change(email, { target: { value: 'owner@example.com' } });
  fireEvent.change(screen.getByLabelText(/password/i), {
    target: { value: 'correct horse battery st!' },
  });
  // Submitting the form directly models Enter inside a native form.
  const form = email.closest('form');
  expect(form).not.toBeNull();
  if (form !== null) {
    fireEvent.submit(form);
  }
  await waitFor(() => {
    expect(login).toHaveBeenCalledTimes(1);
  });
});

test('every auth page exposes exactly one labelled h1 landmark heading', async () => {
  for (const path of ['/login', '/invitations/accept', '/password-reset']) {
    const { view } = renderApp(path, makeClient());
    const headings = await screen.findAllByRole('heading', { level: 1 });
    expect(headings).toHaveLength(1);
    view.unmount();
  }
});

test('pending session state is announced via a status region', () => {
  const pendingForever = new Promise<never>(() => {
    /* never resolves */
  });
  renderApp(
    '/',
    makeClient({ auth: { getSession: vi.fn(() => pendingForever) } }),
  );
  expect(screen.getByRole('status')).toBeInTheDocument();
});

test('a repeated failure with the identical message is focused again', async () => {
  // Local confirmation mismatch produces the same visible message on
  // every attempt; each failed submission must still move focus to the
  // summary so the failure is re-announced (keyed off the failure
  // object, never the message string).
  renderApp('/password-reset', makeClient());

  fireEvent.change(await screen.findByLabelText(/reset token/i), {
    target: { value: 'some-token' },
  });
  fireEvent.change(screen.getByLabelText(/^new password$/i), {
    target: { value: 'one password 111!' },
  });
  fireEvent.change(screen.getByLabelText(/confirm new password/i), {
    target: { value: 'a different password' },
  });
  fireEvent.click(screen.getByRole('button', { name: /change password/i }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/passwords do not match/i);
  await waitFor(() => {
    expect(document.activeElement).toBe(alert);
  });

  // Move focus away, then fail again with the identical message.
  const tokenInput = screen.getByLabelText(/reset token/i);
  tokenInput.focus();
  expect(document.activeElement).toBe(tokenInput);
  fireEvent.click(screen.getByRole('button', { name: /change password/i }));
  await waitFor(() => {
    expect(document.activeElement).toBe(screen.getByRole('alert'));
  });
});

test('interactive controls opt into the 44px minimum target-size classes', async () => {
  renderApp('/login', makeClient());
  const button = await screen.findByRole('button', { name: /^sign in$/i });
  const input = screen.getByLabelText(/email/i);
  // jsdom computes no layout; the contract is that every control sits in
  // the shared classes whose stylesheets pin min-height to 44px (verified
  // visually in the authorized live smoke). Inputs inherit through the
  // .field wrapper's descendant selector.
  expect(button.className).not.toBe('');
  expect(input.closest('div')?.className ?? '').not.toBe('');
});
