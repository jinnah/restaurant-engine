import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import type { ApiResult, SessionResponse } from '@restaurant-engine/api-client';
import {
  apiError,
  envelope,
  makeClient,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

function loginResponse(): SessionResponse {
  const view = sessionView();
  return { user: view.user, csrf_token: view.csrf_token };
}

async function fillAndSubmit() {
  fireEvent.change(await screen.findByLabelText(/email/i), {
    target: { value: 'owner@example.com' },
  });
  fireEvent.change(screen.getByLabelText(/password/i), {
    target: { value: 'correct horse battery st!' },
  });
  fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));
}

test('login establishes the authoritative session before navigating', async () => {
  const login = vi.fn(async () => ok(loginResponse()));
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(apiError(401, null)) // bootstrap: anonymous
    .mockResolvedValue(ok(sessionView())); // establishment + later reads
  const { router } = renderApp(
    '/login',
    makeClient({ auth: { login, getSession } }),
  );

  await fillAndSubmit();

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/');
  });
  expect(login).toHaveBeenCalledExactlyOnceWith({
    email: 'owner@example.com',
    password: 'correct horse battery st!',
  });
  // Authoritative establishment: the session endpoint was consulted again
  // after login, and only after login had resolved.
  expect(getSession.mock.calls.length).toBeGreaterThanOrEqual(2);
  // Defaults make the assertion fail loudly if either call is missing.
  const loginOrder =
    login.mock.invocationCallOrder[0] ?? Number.MAX_SAFE_INTEGER;
  const establishOrder = getSession.mock.invocationCallOrder[1] ?? 0;
  expect(loginOrder).toBeLessThan(establishOrder);
  // The protected landing rendered from the SessionView, not the login body.
  expect(
    await screen.findByRole('heading', { name: /control center/i }),
  ).toBeInTheDocument();
});

test('login preserves a safe next destination', async () => {
  const login = vi.fn(async () => ok(loginResponse()));
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(apiError(401, null))
    .mockResolvedValue(ok(sessionView()));
  const { router } = renderApp(
    '/login?next=' + encodeURIComponent('/dest?page=2'),
    makeClient({ auth: { login, getSession } }),
  );

  await fillAndSubmit();

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/dest');
  });
  expect(router.state.location.search).toBe('?page=2');
});

test('invalid credentials render the neutral summary and keep the form', async () => {
  const client = makeClient(); // default login: 401 with neutral envelope
  renderApp('/login', client);

  await fillAndSubmit();

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Invalid email or password.');
  // The summary receives focus so the failure is announced and reachable.
  await waitFor(() => {
    expect(document.activeElement).toBe(alert);
  });
  expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
});

test('422 field errors map inline to their inputs', async () => {
  const login = vi.fn(async () =>
    apiError(
      422,
      envelope('validation_error', 'Validation failed.', [
        {
          field: 'body.email',
          code: 'value_error',
          message: 'Enter a valid email address.',
        },
      ]),
    ),
  );
  renderApp('/login', makeClient({ auth: { login } }));

  await fillAndSubmit();

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /some fields need attention/i,
  );
  const email = screen.getByLabelText(/email/i);
  expect(email).toHaveAttribute('aria-invalid', 'true');
  expect(email).toHaveAccessibleDescription('Enter a valid email address.');
});

test('session-establishment failure retries only the session fetch', async () => {
  const login = vi.fn(async () => ok(loginResponse()));
  const getSession = vi
    .fn()
    .mockResolvedValueOnce(apiError(401, null)) // bootstrap
    .mockResolvedValueOnce(apiError(503, null)) // establishment fails
    .mockResolvedValue(ok(sessionView())); // retry succeeds
  const { router } = renderApp(
    '/login',
    makeClient({ auth: { login, getSession } }),
  );

  await fillAndSubmit();

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/session could not be loaded/i);
  // Distinct from a credential failure; no invalid-credentials language.
  expect(alert.textContent).not.toMatch(/invalid email or password/i);

  fireEvent.click(
    screen.getByRole('button', { name: /retry loading session/i }),
  );
  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/');
  });
  // Credentials were submitted exactly once; only the session fetch retried.
  expect(login).toHaveBeenCalledTimes(1);
  expect(getSession.mock.calls.length).toBeGreaterThanOrEqual(3);
});

test('submission is disabled while pending, preventing duplicates', async () => {
  let resolveLogin: (value: ApiResult<SessionResponse>) => void = () =>
    undefined;
  const login = vi.fn(
    () =>
      new Promise<ApiResult<SessionResponse>>((resolve) => {
        resolveLogin = resolve;
      }),
  );
  renderApp('/login', makeClient({ auth: { login } }));

  await fillAndSubmit();

  const button = screen.getByRole('button', { name: /signing in/i });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  fireEvent.click(button);
  expect(login).toHaveBeenCalledTimes(1);
  resolveLogin(apiError(401, null));
});
