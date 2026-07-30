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

  test('a request without a Host forwards nothing', async () => {
    const server = await withStub({ body: 'never' });
    const bare = new Request('http://127.0.0.1:3000/api/v1/public/menu');
    bare.headers.delete('host');
    const response = await forwardDevApiRequest(bare);
    expect(response.status).toBe(404);
    expect(server.requests).toHaveLength(0);
  });
});
