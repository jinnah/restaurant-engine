// @vitest-environment node

// Deterministic evidence for the development media-forwarding topology
// (ADR-021): the forwarder reaches the backend through the tenant
// transport with the browser's original Host preserved verbatim, passes
// the backend's response (status, cache policy, validators) through
// untouched, and is disabled in production.

import { afterEach, describe, expect, test, vi } from 'vitest';

import {
  developmentProxyEnabled,
  forwardDevApiRequest,
} from '../../lib/server/dev-api-proxy';
import { startHttpStub, type HttpStub } from './http-stub';

const HOST = 'tandoor.localhost:3000';

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

describe('forwardDevApiRequest', () => {
  test('forwards path, query, and the original tenant Host', async () => {
    const server = await withStub({
      headers: {
        'cache-control': 'public, max-age=3600, immutable',
        'content-type': 'image/webp',
        etag: '"abc"',
      },
      body: 'webp-bytes',
    });
    const response = await forwardDevApiRequest(
      new Request(
        `http://${HOST}/api/v1/public/media/00000000-0000-0000-0000-000000000000/w640?x=1`,
        { headers: { host: HOST, accept: 'image/webp' } },
      ),
    );
    expect(response.status).toBe(200);
    // The backend's centrally assigned cache policy passes through.
    expect(response.headers.get('cache-control')).toBe(
      'public, max-age=3600, immutable',
    );
    expect(response.headers.get('etag')).toBe('"abc"');
    expect(await response.text()).toBe('webp-bytes');
    const seen = server.requests[0];
    expect(seen?.url).toBe(
      '/api/v1/public/media/00000000-0000-0000-0000-000000000000/w640?x=1',
    );
    expect(seen?.headers.host).toBe(HOST);
    expect(seen?.headers.accept).toBe('image/webp');
  });

  test('forwards If-None-Match and passes a 304 through', async () => {
    const server = await withStub({ status: 304, headers: { etag: '"abc"' } });
    const response = await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/public/media/x/w320`, {
        headers: { host: HOST, 'if-none-match': '"abc"' },
      }),
    );
    expect(response.status).toBe(304);
    expect(server.requests[0]?.headers['if-none-match']).toBe('"abc"');
  });

  test('an unreachable backend is a bounded 502, never a hang', async () => {
    vi.stubEnv('STOREFRONT_API_ORIGIN', 'http://127.0.0.1:9');
    const response = await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/public/media/x/w320`, {
        headers: { host: HOST },
      }),
    );
    expect(response.status).toBe(502);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  test('production disables the forwarder with a neutral 404', async () => {
    const server = await withStub({ body: 'never' });
    vi.stubEnv('NODE_ENV', 'production');
    expect(developmentProxyEnabled()).toBe(false);
    const response = await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/public/media/x/w320`, {
        headers: { host: HOST },
      }),
    );
    expect(response.status).toBe(404);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(server.requests).toHaveLength(0);
  });

  test('a path that normalizes outside /api/ forwards nothing', async () => {
    const server = await withStub({ body: 'never' });
    // URL construction normalizes dot segments before the boundary
    // check: /api/../health becomes /health, which is outside the
    // backend API namespace this forwarder exists for.
    const escaping = new Request(`http://${HOST}/api/../health/ready`, {
      headers: { host: HOST },
    });
    expect(new URL(escaping.url).pathname).toBe('/health/ready');
    const response = await forwardDevApiRequest(escaping);
    expect(response.status).toBe(404);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(server.requests).toHaveLength(0);
  });

  test('a request without a Host forwards nothing', async () => {
    const server = await withStub({ body: 'never' });
    const bare = new Request('http://127.0.0.1:3000/api/v1/public/menu');
    bare.headers.delete('host');
    const response = await forwardDevApiRequest(bare);
    expect(response.status).toBe(404);
    expect(server.requests).toHaveLength(0);
  });
});

// M6C (ADR-026 D9): POST forwards for the public ordering surface only,
// with the body and the browser-context evidence preserved verbatim.
describe('forwardDevApiRequest POST', () => {
  test('forwards body, Host, and the browser-context headers verbatim', async () => {
    const server = await withStub({
      status: 201,
      headers: { 'cache-control': 'no-store' },
      body: '{"tracking_token":"tok"}',
    });
    const response = await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/public/orders`, {
        method: 'POST',
        headers: {
          host: HOST,
          'content-type': 'application/json',
          origin: `http://${HOST}`,
          'sec-fetch-site': 'same-origin',
          referer: `http://${HOST}/order`,
        },
        body: '{"idempotency_key":"k"}',
      }),
    );
    expect(response.status).toBe(201);
    expect(await response.text()).toBe('{"tracking_token":"tok"}');
    const seen = server.requests[0];
    expect(seen?.method).toBe('POST');
    expect(seen?.url).toBe('/api/v1/public/orders');
    expect(seen?.body).toBe('{"idempotency_key":"k"}');
    // The backend resolves the tenant from Host and judges the unsafe
    // request from exactly this evidence — all preserved verbatim.
    expect(seen?.headers.host).toBe(HOST);
    expect(seen?.headers['content-type']).toBe('application/json');
    expect(seen?.headers.origin).toBe(`http://${HOST}`);
    expect(seen?.headers['sec-fetch-site']).toBe('same-origin');
    expect(seen?.headers.referer).toBe(`http://${HOST}/order`);
  });

  test('cookies and authorization never travel on the POST leg', async () => {
    const server = await withStub({ body: '{}' });
    await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/public/orders`, {
        method: 'POST',
        headers: {
          host: HOST,
          'content-type': 'application/json',
          cookie: 'session=secret',
          authorization: 'Bearer secret',
        },
        body: '{}',
      }),
    );
    const seen = server.requests[0];
    expect(seen?.headers.cookie).toBeUndefined();
    expect(seen?.headers.authorization).toBeUndefined();
  });

  test('POST outside /api/v1/public/ forwards nothing', async () => {
    const server = await withStub({ body: 'never' });
    const response = await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/auth/login`, {
        method: 'POST',
        headers: { host: HOST, 'content-type': 'application/json' },
        body: '{}',
      }),
    );
    expect(response.status).toBe(404);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(server.requests).toHaveLength(0);
  });

  test('production disables the POST leg like everything else', async () => {
    const server = await withStub({ body: 'never' });
    vi.stubEnv('NODE_ENV', 'production');
    const response = await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/public/orders`, {
        method: 'POST',
        headers: { host: HOST },
        body: '{}',
      }),
    );
    expect(response.status).toBe(404);
    expect(server.requests).toHaveLength(0);
  });

  test('an unreachable backend is a bounded 502 on POST too', async () => {
    vi.stubEnv('STOREFRONT_API_ORIGIN', 'http://127.0.0.1:9');
    const response = await forwardDevApiRequest(
      new Request(`http://${HOST}/api/v1/public/orders`, {
        method: 'POST',
        headers: { host: HOST },
        body: '{}',
      }),
    );
    expect(response.status).toBe(502);
  });
});
