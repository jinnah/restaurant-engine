// @vitest-environment node

// Permanent tenant-isolation contracts of the server transport (ADR-021):
// the incoming Host travels to the backend verbatim, every alternative
// tenant-selection channel is stripped, and every request carries
// `cache: "no-store"`. Asserted against a live loopback stub, because the
// wire is the contract.

import { afterEach, describe, expect, test } from 'vitest';

import {
  createTenantFetch,
  normalizeTenantRequest,
  wireHeaders,
} from '../../lib/server/tenant-fetch';
import { startHttpStub, type HttpStub } from './http-stub';

const HOST = 'tandoor.localhost:3000';

let stub: HttpStub | null = null;

afterEach(async () => {
  if (stub !== null) {
    await stub.close();
    stub = null;
  }
});

describe('wireHeaders (the sanitization policy, pure)', () => {
  test('forwards the tenant host exactly and strips every alternative channel', () => {
    const incoming = new Headers({
      accept: 'application/json',
      cookie: 'session=secret',
      authorization: 'Bearer secret',
      'x-business-id': '123',
      'x-forwarded-host': 'evil.example',
      'x-forwarded-for': '10.0.0.1',
      'x-forwarded-proto': 'https',
      forwarded: 'host=evil.example',
      'x-real-ip': '10.0.0.1',
      host: 'wrong.example',
    });
    const wire = wireHeaders(incoming, HOST);
    expect(wire['host']).toBe(HOST);
    expect(wire).toEqual({ host: HOST, accept: 'application/json' });
  });
});

describe('normalizeTenantRequest', () => {
  test('stamps cache no-store on every request', () => {
    const plain = normalizeTenantRequest('http://127.0.0.1:9/x');
    expect(plain.cache).toBe('no-store');
    const fromRequest = normalizeTenantRequest(
      new Request('http://127.0.0.1:9/x', { cache: 'force-cache' }),
    );
    expect(fromRequest.cache).toBe('no-store');
  });
});

describe('createTenantFetch (live wire behavior)', () => {
  test('sends the tenant Host and no tenant-selection alternatives', async () => {
    stub = await startHttpStub({ body: '{"ok":true}' });
    const tenantFetch = createTenantFetch(HOST);
    const response = await tenantFetch(
      new Request(`${stub.origin}/api/v1/public/storefront`, {
        headers: {
          accept: 'application/json',
          cookie: 'session=secret',
          'x-forwarded-host': 'evil.example',
          'x-business-id': 'b-1',
        },
      }),
    );
    expect(response.status).toBe(200);
    expect(stub.requests).toHaveLength(1);
    const seen = stub.requests[0];
    expect(seen?.headers.host).toBe(HOST);
    const seenNames = (seen?.rawHeaderNames ?? []).map((n) => n.toLowerCase());
    expect(seenNames).not.toContain('cookie');
    expect(seenNames).not.toContain('authorization');
    expect(seenNames).not.toContain('x-business-id');
    expect(seenNames.some((n) => n.startsWith('x-forwarded-'))).toBe(false);
    expect(seenNames).not.toContain('forwarded');
  });

  test('maps status, headers, and body onto a Response', async () => {
    stub = await startHttpStub({
      status: 404,
      headers: { 'cache-control': 'no-store', 'x-request-id': 'abc' },
      body: '{"error":{"code":"not_found"}}',
    });
    const tenantFetch = createTenantFetch(HOST);
    const response = await tenantFetch(`${stub.origin}/api/v1/public/menu`);
    expect(response.status).toBe(404);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(response.headers.get('x-request-id')).toBe('abc');
    expect(await response.json()).toEqual({ error: { code: 'not_found' } });
  });

  test('HEAD responses carry no body', async () => {
    stub = await startHttpStub({ headers: { etag: '"v1"' } });
    const tenantFetch = createTenantFetch(HOST);
    const response = await tenantFetch(
      new Request(`${stub.origin}/api/v1/public/storefront`, {
        method: 'HEAD',
      }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get('etag')).toBe('"v1"');
    expect(await response.text()).toBe('');
  });

  test('rejects unsafe methods and bodies (read-only transport)', async () => {
    const tenantFetch = createTenantFetch(HOST);
    await expect(
      tenantFetch(
        new Request('http://127.0.0.1:9/api/v1/public/storefront', {
          method: 'POST',
          body: '{}',
        }),
      ),
    ).rejects.toThrow(/read-only/);
  });

  test('a stalled backend rejects at the deadline', async () => {
    stub = await startHttpStub({ delayMs: 5_000 });
    const tenantFetch = createTenantFetch(HOST, { timeoutMs: 100 });
    await expect(
      tenantFetch(`${stub.origin}/api/v1/public/storefront`),
    ).rejects.toThrow(/timeout/);
  });

  test('a refused connection rejects rather than hanging', async () => {
    // Port 9 (discard) on loopback: nothing listens in these suites.
    const tenantFetch = createTenantFetch(HOST, { timeoutMs: 1_000 });
    await expect(
      tenantFetch('http://127.0.0.1:9/api/v1/public/storefront'),
    ).rejects.toThrow(/tenant fetch failed/);
  });
});
