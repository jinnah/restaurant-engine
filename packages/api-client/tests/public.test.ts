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

const MENU = {
  business: SITE,
  categories: [
    {
      id: '11111111-1111-1111-1111-111111111111',
      name: 'Curries',
      description: null,
      items: [
        {
          id: '22222222-2222-2222-2222-222222222222',
          name: 'Samosa',
          description: 'Crisp pastry',
          price_minor: 350,
          is_available: true,
          is_orderable: true,
          dietary_tags: ['halal'],
          image: {
            alt_text: 'Golden samosa',
            width: 1200,
            height: 800,
            url: '/api/v1/public/media/33333333-3333-3333-3333-333333333333/canonical',
            variants: [
              {
                variant: 'w320' as const,
                width: 320,
                height: 213,
                url: '/api/v1/public/media/33333333-3333-3333-3333-333333333333/w320',
              },
            ],
          },
          modifier_groups: [
            {
              id: '44444444-4444-4444-4444-444444444444',
              name: 'Spice level',
              min_select: 1,
              max_select: 1,
              options: [
                {
                  id: '55555555-5555-5555-5555-555555555555',
                  name: 'Mild',
                  price_delta_minor: 0,
                },
              ],
            },
          ],
        },
      ],
    },
  ],
  featured_item_ids: ['22222222-2222-2222-2222-222222222222'],
};

describe('public.getMenu', () => {
  it('GETs the public menu with no tenant-selection input', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, MENU), requests);

    const result = await client.public.getMenu();

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/public/menu');
    // Same invariant as getSite: nothing the caller supplies can select a
    // tenant — the Host does, server-side.
    expect([...url.searchParams.keys()]).toEqual([]);
    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.headers.get('X-Business-Slug')).toBeNull();
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBeNull();
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(MENU);
      // Typed all the way down through the nested projection.
      expect(result.data.categories[0]?.items[0]?.is_orderable).toBe(true);
      expect(
        result.data.categories[0]?.items[0]?.image?.variants[0]?.width,
      ).toBe(320);
      expect(result.data.featured_item_ids).toHaveLength(1);
      // Image URLs arrive relative and same-origin, so no builder is needed.
      expect(result.data.categories[0]?.items[0]?.image?.url).toMatch(
        /^\/api\/v1\/public\/media\//,
      );
    }
  });

  it('narrows the neutral not_found on 404', async () => {
    const client = clientCapturing(jsonResponse(404, notFound()));
    const result = await client.public.getMenu();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.envelope?.error.code).toBe('not_found');
    }
  });

  it('reports a network failure without throwing', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('offline')),
    });
    const result = await client.public.getMenu();
    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });

  it('handles a non-JSON body on an error status', async () => {
    const client = clientCapturing(
      new Response('<html>gateway</html>', {
        status: 502,
        headers: { 'Content-Type': 'text/html' },
      }),
    );
    const result = await client.public.getMenu();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(502);
      expect(result.envelope).toBeNull();
    }
  });
});
