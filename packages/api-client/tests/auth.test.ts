// Auth facade behavior with an injected fetch — no network, no backend.
// Covers: typed payloads, the CSRF header on logout, credentials mode,
// the 401/403 envelopes, and network failure.

import { describe, expect, it } from 'vitest';

import { createApiClient, type ErrorEnvelope } from '../src/index';

const BASE_URL = 'http://api.test';

const SESSION_BODY = {
  user: {
    id: '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e',
    email: 'owner@example.com',
    display_name: 'Owner',
    is_platform_admin: false,
  },
  csrf_token: 'csrf-token-value',
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function envelope(code: ErrorEnvelope['error']['code']): ErrorEnvelope {
  return {
    error: {
      code,
      message: 'irrelevant for the test',
      field_errors: [],
      correlation_id: 'corr-1',
      details: null,
    },
  };
}

function clientCapturing(response: Response, requests: Request[] = []) {
  return createApiClient({
    baseUrl: BASE_URL,
    fetch: (input: Request) => {
      requests.push(input);
      return Promise.resolve(response);
    },
  });
}

describe('auth.login', () => {
  it('posts the credentials and returns the typed session payload', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, SESSION_BODY), requests);

    const result = await client.auth.login({
      email: 'owner@example.com',
      password: 'correct horse battery st!',
    });

    expect(requests[0]?.url).toBe(`${BASE_URL}/api/v1/auth/login`);
    expect(requests[0]?.method).toBe('POST');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.user.email).toBe('owner@example.com');
      expect(result.data.csrf_token).toBe('csrf-token-value');
    }
  });

  it('sends credentials so the browser stores the HttpOnly cookie', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, SESSION_BODY), requests);

    await client.auth.login({ email: 'a@b.co', password: 'p'.repeat(12) });

    expect(requests[0]?.credentials).toBe('include');
  });

  it('narrows the uniform invalid_credentials envelope on 401', async () => {
    const client = clientCapturing(
      jsonResponse(401, envelope('invalid_credentials')),
    );

    const result = await client.auth.login({
      email: 'a@b.co',
      password: 'wrong-password',
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(401);
      expect(result.envelope?.error.code).toBe('invalid_credentials');
    }
  });

  it('reports a network failure as a null-status failure', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('connection refused')),
    });

    const result = await client.auth.login({
      email: 'a@b.co',
      password: 'irrelevant-here',
    });

    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});

describe('auth.logout', () => {
  it('sends the CSRF synchronizer token header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { status: 'logged_out' }),
      requests,
    );

    const result = await client.auth.logout('csrf-token-value');

    expect(requests[0]?.url).toBe(`${BASE_URL}/api/v1/auth/logout`);
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token-value');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.status).toBe('logged_out');
    }
  });

  it('narrows the csrf_rejected envelope on 403', async () => {
    const client = clientCapturing(
      jsonResponse(403, envelope('csrf_rejected')),
    );

    const result = await client.auth.logout('stale-token');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(403);
      expect(result.envelope?.error.code).toBe('csrf_rejected');
    }
  });
});

describe('auth.getSession', () => {
  it('returns the enriched session view with memberships', async () => {
    const requests: Request[] = [];
    const sessionView = {
      ...SESSION_BODY,
      memberships: [
        {
          restaurant_id: '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e',
          restaurant_slug: 'juniper',
          restaurant_name: 'Juniper',
          role: 'owner',
          restaurant_status: 'active',
        },
      ],
    };
    const client = clientCapturing(jsonResponse(200, sessionView), requests);

    const result = await client.auth.getSession();

    expect(requests[0]?.url).toBe(`${BASE_URL}/api/v1/auth/session`);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.user.display_name).toBe('Owner');
      expect(result.data.memberships[0]?.restaurant_slug).toBe('juniper');
      expect(result.data.memberships[0]?.role).toBe('owner');
    }
  });

  it('narrows authentication_required on 401', async () => {
    const client = clientCapturing(
      jsonResponse(401, envelope('authentication_required')),
    );

    const result = await client.auth.getSession();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.envelope?.error.code).toBe('authentication_required');
    }
  });
});
