// Client/proxy invariants (ADR-015) proven through the REAL generated
// facade with an injected fetch. Node's Request cannot carry a relative
// URL, so these tests pin the invariants via the page origin and the
// exported base-URL constant; the literal origin-relative form through
// the running Vite proxy is exercised by the separately authorized live
// smoke step.

import { vi, expect, test } from 'vitest';
import { createApiClient } from '@restaurant-engine/api-client';
import { API_BASE_URL } from '../src/api/client';

function capturingClient(status = 200, body: unknown = { ok: true }) {
  const requests: Request[] = [];
  const client = createApiClient({
    baseUrl: window.location.origin,
    fetch: vi.fn((input: Request) => {
      requests.push(input);
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  });
  return { client, requests };
}

test('the production client is configured origin-relative', () => {
  expect(API_BASE_URL).toBe('');
});

test('every facade request stays under the page origin on an /api path', async () => {
  const { client, requests } = capturingClient(404, {
    error: {
      code: 'not_found',
      message: 'x',
      field_errors: [],
      correlation_id: null,
    },
  });

  await client.auth.getSession();
  await client.invitations.preview({ token: 't' });
  await client.passwordResets.redeem({
    token: 't',
    new_password: 'p'.repeat(12),
  });

  for (const request of requests) {
    const url = new URL(request.url);
    expect(url.origin).toBe(window.location.origin);
    expect(url.pathname.startsWith('/api/')).toBe(true);
  }
  expect(requests).toHaveLength(3);
});

test('every request carries credentials so the HttpOnly cookie travels', async () => {
  const { client, requests } = capturingClient();
  await client.auth.getSession();
  expect(requests[0]?.credentials).toBe('include');
});

test('public mutations never attach the CSRF header', async () => {
  const { client, requests } = capturingClient(404, {
    error: {
      code: 'not_found',
      message: 'x',
      field_errors: [],
      correlation_id: null,
    },
  });

  await client.invitations.preview({ token: 't' });
  await client.invitations.accept({
    token: 't',
    display_name: 'N',
    password: 'p'.repeat(12),
  });
  await client.passwordResets.redeem({
    token: 't',
    new_password: 'p'.repeat(12),
  });

  for (const request of requests) {
    expect(request.headers.get('X-CSRF-Token')).toBeNull();
  }
  expect(requests).toHaveLength(3);
});

test('authenticated unsafe operations attach the provided CSRF token', async () => {
  const { client, requests } = capturingClient();

  await client.auth.logout('csrf-current');
  await client.invitations.acceptExisting({ token: 't' }, 'csrf-current');

  for (const request of requests) {
    expect(request.headers.get('X-CSRF-Token')).toBe('csrf-current');
  }
  expect(requests).toHaveLength(2);
});
