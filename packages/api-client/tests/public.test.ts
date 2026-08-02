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

const STOREFRONT = {
  business: SITE,
  design_variant: 'classic' as const,
  theme: { accent: '#146b5c' },
  sections: [
    {
      id: 'hero-main',
      type: 'hero' as const,
      props: {
        heading: 'Shalik Kitchen',
        subheading: null,
        image: {
          alt_text: 'The dining room',
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
        primary_action: 'view_menu' as const,
      },
    },
    {
      id: 'story-main',
      type: 'story' as const,
      props: { heading: 'Our story', body: 'A family kitchen.' },
    },
  ],
};

describe('public.getStorefront', () => {
  it('GETs the public storefront with no tenant-selection input', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, STOREFRONT), requests);

    const result = await client.public.getStorefront();

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/public/storefront');
    // Same invariant as getSite/getMenu: nothing the caller supplies can
    // select a tenant — the Host does, server-side.
    expect([...url.searchParams.keys()]).toEqual([]);
    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.headers.get('X-Business-Slug')).toBeNull();
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBeNull();
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(STOREFRONT);
      // Typed through the discriminated section union.
      const hero = result.data.sections[0];
      expect(hero?.type).toBe('hero');
      if (hero?.type === 'hero') {
        expect(hero.props.primary_action).toBe('view_menu');
        expect(hero.props.image?.url).toMatch(/^\/api\/v1\/public\/media\//);
      }
    }
  });

  it('narrows the neutral not_found on 404 (unpublished or unknown)', async () => {
    const client = clientCapturing(jsonResponse(404, notFound()));
    const result = await client.public.getStorefront();
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
    const result = await client.public.getStorefront();
    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});

describe('public.getAvailability', () => {
  const AVAILABILITY = {
    business: SITE,
    is_open_now: true,
    closes_at: '2026-08-01T21:00:00Z',
    next_opens_at: null,
    weekly: [{ day_of_week: 0, opens_minute: 660, closes_minute: 1260 }],
    exceptions: [
      { exception_date: '2026-08-20', intervals: [], note: 'Closed for Eid' },
    ],
    pickup: { enabled: false, asap_enabled: true, next_pickup_at: null },
  };

  it('GETs the availability with no tenant-selection input', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, AVAILABILITY), requests);

    const result = await client.public.getAvailability();

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/public/availability');
    expect([...url.searchParams.keys()]).toEqual([]);
    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBeNull();
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.is_open_now).toBe(true);
      expect(result.data.weekly[0]?.day_of_week).toBe(0);
      expect(result.data.exceptions[0]?.note).toBe('Closed for Eid');
      expect(result.data.pickup.enabled).toBe(false);
    }
  });

  it('narrows the neutral not_found on 404 (inactive or unknown host)', async () => {
    const client = clientCapturing(jsonResponse(404, notFound()));
    const result = await client.public.getAvailability();
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
    const result = await client.public.getAvailability();
    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});

describe('public.placeOrder', () => {
  const PLACE = {
    idempotency_key: '3e0d8a4e-6f3c-4b12-9a67-2c1d5e8f0a4b',
    lines: [
      {
        item_id: '00000000-0000-0000-0000-000000000101',
        quantity: 2,
        option_ids: [],
        item_instructions: null,
      },
    ],
    customer_name: 'Amina Rahman',
    customer_phone: '(716) 555-0142',
    customer_email: null,
    order_instructions: null,
    consent_updates: true,
    consent_marketing: false,
    pickup_kind: 'asap' as const,
    requested_pickup_at: null,
    expected_total_minor: 2500,
  };

  const PLACED = {
    tracking_token: 'the-one-time-token',
    order: {
      business: SITE,
      order_number: 1,
      status: 'submitted',
      placed_at: '2026-08-02T16:00:00Z',
      business_timezone: 'America/New_York',
      pickup_kind: 'asap',
      promised_pickup_at: '2026-08-02T16:20:00Z',
      currency: 'USD',
      subtotal_minor: 2500,
      tax_minor: 0,
      total_minor: 2500,
      lines: [
        {
          display_name: 'Clay-oven lamb',
          quantity: 2,
          base_price_minor: 1250,
          options: [],
          line_total_minor: 2500,
        },
      ],
    },
  };

  it('POSTs the placement with no tenant-selection input (M6A)', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(201, PLACED), requests);

    const result = await client.public.placeOrder(PLACE);

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/public/orders');
    expect(requests[0]?.method).toBe('POST');
    // Anonymous placement: no synchronizer token, no tenant header — the
    // Host (and the browser-context evidence) is transport, not facade.
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBeNull();
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.tracking_token).toBe('the-one-time-token');
      expect(result.data.order.order_number).toBe(1);
      expect(result.data.order.total_minor).toBe(2500);
    }
  });

  it('narrows the typed 409s (cart_stale and friends)', async () => {
    const client = clientCapturing(
      jsonResponse(409, {
        error: {
          code: 'price_changed',
          message: 'Prices changed while you were ordering.',
          field_errors: [],
          correlation_id: 'x',
          details: { total_minor: 2600, expected_total_minor: 2500 },
        },
      }),
    );
    const result = await client.public.placeOrder(PLACE);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('price_changed');
    }
  });

  it('reports a network failure without throwing', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('offline')),
    });
    const result = await client.public.placeOrder(PLACE);
    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });

  it('getOrder addresses the tracking route by token (M6B)', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, PLACED.order), requests);
    const result = await client.public.getOrder('the-token');
    expect(new URL(requests[0]!.url).pathname).toBe(
      '/api/v1/public/orders/the-token',
    );
    expect(requests[0]?.method).toBe('GET');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.status).toBe('submitted');
      // PII-free by design: the projection carries no customer fields.
      expect(result.data).not.toHaveProperty('customer_name');
    }
  });

  it('cancelOrder POSTs the cancel command and narrows invalid_state', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { ...PLACED.order, status: 'cancelled' }),
      requests,
    );
    const result = await client.public.cancelOrder('the-token');
    expect(new URL(requests[0]!.url).pathname).toBe(
      '/api/v1/public/orders/the-token/cancel',
    );
    expect(requests[0]?.method).toBe('POST');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.status).toBe('cancelled');
    }
    const refused = clientCapturing(
      jsonResponse(409, {
        error: {
          code: 'invalid_state',
          message: 'This order can no longer be cancelled online.',
          field_errors: [],
          correlation_id: 'x',
        },
      }),
    );
    const late = await refused.public.cancelOrder('the-token');
    expect(late.ok).toBe(false);
    if (!late.ok) {
      expect(late.envelope?.error.code).toBe('invalid_state');
    }
  });

  it('getPickupSlots GETs the bounded listing with no tenant input', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { slots: ['2026-08-02T17:15:00Z'] }),
      requests,
    );
    const result = await client.public.getPickupSlots();
    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/public/pickup-slots');
    expect([...url.searchParams.keys()]).toEqual([]);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.slots).toEqual(['2026-08-02T17:15:00Z']);
    }
  });
});
