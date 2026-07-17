// Public storefront facade behavior with an injected fetch — no network.
// The tenant is resolved server-side from the destination Host; getSite
// takes no argument and sends no tenant-selection input of its own.

import { describe, expect, it } from 'vitest';

import { createApiClient, type ErrorEnvelope } from '../src/index';

const BASE_URL = 'http://shalik.localhost';

const SITE = {
  name: 'Shalik',
  slug: 'shalik',
  timezone: 'America/New_York',
  currency: 'USD',
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function notFound(): ErrorEnvelope {
  return {
    error: {
      code: 'not_found',
      message: 'Not found.',
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

describe('public.getSite', () => {
  it('GETs the public site with no tenant-selection input', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, SITE), requests);

    const result = await client.public.getSite();

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/public/site');
    // No tenant selection smuggled into the query string.
    expect([...url.searchParams.keys()]).toEqual([]);
    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.headers.get('X-Business-Slug')).toBeNull();
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBeNull();
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(SITE);
    }
  });

  it('narrows the neutral not_found on 404', async () => {
    const client = clientCapturing(jsonResponse(404, notFound()));
    const result = await client.public.getSite();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.envelope?.error.code).toBe('not_found');
    }
  });
});
