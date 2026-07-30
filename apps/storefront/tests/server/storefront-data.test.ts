// @vitest-environment node

// The server data-access boundary end to end: the real api-client facade
// over the real tenant transport against a live stub — proving the Host
// travels through the whole stack — plus the three-way outcome mapping
// (ok / not-found / unavailable) the pages render from.

import { afterEach, describe, expect, test, vi } from 'vitest';

import {
  getPublishedStorefront,
  loadPublicMenu,
  loadPublishedStorefront,
} from '../../lib/server/storefront-data';
import { startHttpStub, type HttpStub } from './http-stub';

const HOST = 'tandoor.localhost:3000';

// The cached wrappers re-derive the Host from the request context; tests
// stand in for that context here.
vi.mock('next/headers', () => ({
  headers: async () => new Headers({ host: HOST }),
}));

const STOREFRONT_BODY = JSON.stringify({
  business: {
    name: 'Tandoor House',
    slug: 'tandoor',
    timezone: 'America/New_York',
    currency: 'USD',
  },
  design_variant: 'classic',
  theme: { accent: '#a34b2a' },
  sections: [],
});

let stub: HttpStub | null = null;

afterEach(async () => {
  vi.unstubAllEnvs();
  if (stub !== null) {
    await stub.close();
    stub = null;
  }
});

async function withStub(plan: Parameters<typeof startHttpStub>[0]) {
  stub = await startHttpStub(plan);
  vi.stubEnv('STOREFRONT_API_ORIGIN', stub.origin);
  return stub;
}

describe('loadPublishedStorefront', () => {
  test('a 200 maps to ok, requested with the tenant Host', async () => {
    const server = await withStub({ body: STOREFRONT_BODY });
    const result = await loadPublishedStorefront(HOST);
    expect(result.kind).toBe('ok');
    if (result.kind === 'ok') {
      expect(result.data.business.slug).toBe('tandoor');
      expect(result.data.design_variant).toBe('classic');
    }
    expect(server.requests).toHaveLength(1);
    expect(server.requests[0]?.url).toBe('/api/v1/public/storefront');
    expect(server.requests[0]?.headers.host).toBe(HOST);
  });

  test('the neutral backend 404 maps to not-found', async () => {
    await withStub({
      status: 404,
      body: JSON.stringify({
        error: { code: 'not_found', message: 'Not found.' },
      }),
    });
    expect(await loadPublishedStorefront(HOST)).toEqual({ kind: 'not-found' });
  });

  test('a backend 500 maps to unavailable', async () => {
    await withStub({ status: 500, body: '{}' });
    expect(await loadPublishedStorefront(HOST)).toEqual({
      kind: 'unavailable',
    });
  });

  test('an unreachable backend maps to unavailable', async () => {
    vi.stubEnv('STOREFRONT_API_ORIGIN', 'http://127.0.0.1:9');
    expect(await loadPublishedStorefront(HOST)).toEqual({
      kind: 'unavailable',
    });
  });

  test('a missing Host is not-found without any backend call', async () => {
    const server = await withStub({ body: STOREFRONT_BODY });
    expect(await loadPublishedStorefront(null)).toEqual({ kind: 'not-found' });
    expect(server.requests).toHaveLength(0);
  });
});

describe('loadPublicMenu', () => {
  test('requests the public menu with the tenant Host', async () => {
    const server = await withStub({
      body: JSON.stringify({
        business: {
          name: 'Tandoor House',
          slug: 'tandoor',
          timezone: 'America/New_York',
          currency: 'USD',
        },
        categories: [],
        featured_item_ids: [],
      }),
    });
    const result = await loadPublicMenu(HOST);
    expect(result.kind).toBe('ok');
    expect(server.requests[0]?.url).toBe('/api/v1/public/menu');
    expect(server.requests[0]?.headers.host).toBe(HOST);
  });
});

describe('getPublishedStorefront (request-context wrapper)', () => {
  test('derives the Host from the request headers', async () => {
    const server = await withStub({ body: STOREFRONT_BODY });
    const result = await getPublishedStorefront();
    expect(result.kind).toBe('ok');
    expect(server.requests[0]?.headers.host).toBe(HOST);
  });
});
