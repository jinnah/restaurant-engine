import { fireEvent, screen } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import {
  adminSessionView,
  apiError,
  envelope,
  makeClient,
  ok,
} from './support/mockClient';
import { renderApp } from './support/render';

function adminClient(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
    ...overrides,
  });
}

test('issuing a reset token reveals it once with the authority warning', async () => {
  const issuePasswordReset = vi.fn(async () =>
    ok(
      {
        email: 'locked.out@example.com',
        token: 'reset-token-xyz789',
        expires_at: '2026-07-19T01:00:00Z',
      },
      201,
    ),
  );
  renderApp(
    '/platform/recovery',
    adminClient({ platform: { issuePasswordReset } }),
  );

  // The page states the account-takeover-equivalent authority up front.
  expect(
    await screen.findByText(/same authority as taking the account over/i),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText(/account email/i), {
    target: { value: 'locked.out@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue reset token/i }));

  expect(await screen.findByText('reset-token-xyz789')).toBeInTheDocument();
  expect(screen.getByText(/shown once/i)).toBeInTheDocument();
  expect(issuePasswordReset).toHaveBeenCalledWith(
    { email: 'locked.out@example.com' },
    'csrf-token-1',
  );

  fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
  expect(screen.queryByText('reset-token-xyz789')).toBeNull();
});

test('an unknown or refused account surfaces the neutral message', async () => {
  const issuePasswordReset = vi.fn(async () =>
    apiError(404, envelope('not_found', 'No eligible account was found.')),
  );
  renderApp(
    '/platform/recovery',
    adminClient({ platform: { issuePasswordReset } }),
  );

  fireEvent.change(await screen.findByLabelText(/account email/i), {
    target: { value: 'nobody@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue reset token/i }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/no eligible account/i);
  expect(alert).toHaveFocus();
});

test('a new issuance discards the previous reset token', async () => {
  const issuePasswordReset = vi
    .fn()
    .mockResolvedValueOnce(
      ok({
        email: 'a@example.com',
        token: 'first-reset',
        expires_at: '2026-07-19T01:00:00Z',
      }),
    )
    .mockResolvedValueOnce(
      ok({
        email: 'b@example.com',
        token: 'second-reset',
        expires_at: '2026-07-19T01:00:00Z',
      }),
    );
  renderApp(
    '/platform/recovery',
    adminClient({ platform: { issuePasswordReset } }),
  );

  fireEvent.change(await screen.findByLabelText(/account email/i), {
    target: { value: 'a@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue reset token/i }));
  await screen.findByText('first-reset');

  fireEvent.change(screen.getByLabelText(/account email/i), {
    target: { value: 'b@example.com' },
  });
  fireEvent.click(screen.getByRole('button', { name: /issue reset token/i }));
  await screen.findByText('second-reset');
  expect(screen.queryByText('first-reset')).toBeNull();
});
