// Platform + businesses facade behavior with an injected fetch — no
// network, no backend. Covers request shape (path/CSRF/body), success
// payloads, and the 403/404/409 envelope narrowing.

import { describe, expect, it } from 'vitest';

import { createApiClient, type ErrorEnvelope } from '../src/index';

const BASE_URL = 'http://api.test';
const BID = '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';

const BUSINESS = {
  id: BID,
  name: 'Juniper',
  slug: 'juniper',
  status: 'provisioning',
  timezone: 'America/New_York',
  currency: 'USD',
  created_at: '2026-07-16T00:00:00Z',
  updated_at: '2026-07-16T00:00:00Z',
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
      message: 'irrelevant',
      field_errors: [],
      correlation_id: 'c',
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

describe('platform.createBusiness', () => {
  it('posts the body with the CSRF header and credentials', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(201, BUSINESS), requests);

    const result = await client.platform.createBusiness(
      { name: 'Juniper', slug: 'juniper' },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(`${BASE_URL}/api/v1/platform/businesses`);
    expect(requests[0]?.method).toBe('POST');
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(requests[0]?.credentials).toBe('include');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.status).toBe('provisioning');
    }
  });

  it('narrows conflict on 409', async () => {
    const client = clientCapturing(jsonResponse(409, envelope('conflict')));
    const result = await client.platform.createBusiness(
      { name: 'X', slug: 'taken' },
      'csrf',
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('conflict');
    }
  });

  it('narrows permission_denied on 403', async () => {
    const client = clientCapturing(
      jsonResponse(403, envelope('permission_denied')),
    );
    const result = await client.platform.createBusiness(
      { name: 'X', slug: 'x-slug' },
      'csrf',
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.envelope?.error.code).toBe('permission_denied');
    }
  });
});

describe('platform.listBusinesses', () => {
  it('passes limit and offset as query params', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { items: [], total: 0, limit: 10, offset: 20 }),
      requests,
    );

    const result = await client.platform.listBusinesses({
      limit: 10,
      offset: 20,
    });

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/platform/businesses');
    expect(url.searchParams.get('limit')).toBe('10');
    expect(url.searchParams.get('offset')).toBe('20');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.total).toBe(0);
    }
  });
});

describe('platform lifecycle transitions', () => {
  it.each(['activate', 'suspend', 'reactivate', 'close'] as const)(
    '%s posts an empty body to the right path with the CSRF header',
    async (verb) => {
      const requests: Request[] = [];
      const client = clientCapturing(
        jsonResponse(200, { ...BUSINESS, status: 'active' }),
        requests,
      );

      const result = await client.platform[verb](BID, 'csrf-token');

      expect(requests[0]?.url).toBe(
        `${BASE_URL}/api/v1/platform/businesses/${BID}/${verb}`,
      );
      expect(requests[0]?.method).toBe('POST');
      expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
      expect(result.ok).toBe(true);
    },
  );

  it('narrows invalid_state on 409', async () => {
    const client = clientCapturing(
      jsonResponse(409, envelope('invalid_state')),
    );
    const result = await client.platform.close(BID, 'csrf');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.envelope?.error.code).toBe('invalid_state');
    }
  });
});

describe('businesses.get', () => {
  it('reads the member business', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, BUSINESS), requests);

    const result = await client.businesses.get(BID);

    expect(requests[0]?.url).toBe(`${BASE_URL}/api/v1/businesses/${BID}`);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.slug).toBe('juniper');
    }
  });

  it('narrows not_found on 404 (nonmember or nonexistent)', async () => {
    const client = clientCapturing(jsonResponse(404, envelope('not_found')));
    const result = await client.businesses.get(BID);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.envelope?.error.code).toBe('not_found');
    }
  });
});
