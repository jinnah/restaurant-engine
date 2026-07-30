// Tenant-safe server transport for storefront → backend requests (ADR-021).
//
// The backend resolves the tenant from the request Host and nothing else
// (ADR-013), so the one job of this transport is to deliver the *incoming*
// request's Host to the backend verbatim while the connection itself goes
// to the configured API origin. It is built directly on `node:http(s)`
// rather than global `fetch`, for two load-bearing reasons:
//
// 1. **Host control is guaranteed.** WHATWG fetch treats `Host` as a
//    forbidden request header, so a Host set through `fetch` headers is
//    silently dropped by the runtime. `node:http` sends exactly the
//    headers it is given.
// 2. **Framework caching is structurally impossible.** Next.js patches
//    global `fetch` with its data cache, whose identity is the URL — and
//    every tenant shares the same backend URL, so any framework-level
//    caching would cross tenants (the ADR-013 rule that a cache key must
//    include the resolved Business). A transport that never touches
//    `fetch` cannot participate in that cache, per request or otherwise.
//
// The transport is deliberately read-only (GET/HEAD, no body): the public
// storefront surface is read-only, and refusing anything else keeps this
// primitive from ever becoming a general proxy.

import { Buffer } from 'node:buffer';
import http from 'node:http';
import https from 'node:https';

export const SERVER_FETCH_TIMEOUT_MS = 5_000;

// Request headers that must never travel to the backend from this
// transport. `host` is stripped here because the tenant host is applied
// explicitly afterwards; cookies and authorization have no business on the
// anonymous public surface; forwarded and tenant-selection headers are the
// alternative resolution channels ADR-013 forbids.
const STRIPPED_REQUEST_HEADERS = new Set([
  'host',
  'cookie',
  'authorization',
  'forwarded',
  'x-business-id',
  'x-real-ip',
]);
const STRIPPED_REQUEST_PREFIX = 'x-forwarded-';

// Hop-by-hop headers that describe the upstream connection, not the
// representation; they must not be copied onto a buffered Response.
const STRIPPED_RESPONSE_HEADERS = new Set([
  'connection',
  'keep-alive',
  'transfer-encoding',
  'te',
  'trailer',
  'upgrade',
  'proxy-authenticate',
  'proxy-authorization',
]);

function isStrippedRequestHeader(name: string): boolean {
  const lower = name.toLowerCase();
  return (
    STRIPPED_REQUEST_HEADERS.has(lower) ||
    lower.startsWith(STRIPPED_REQUEST_PREFIX)
  );
}

/**
 * The sanitized wire form of one outgoing backend request: the surviving
 * request headers plus the tenant Host, exactly as `node:http` will send
 * them. Exported as a pure function so the permanent tenant-isolation
 * tests can assert the policy without a socket.
 */
export function wireHeaders(
  requestHeaders: Headers,
  tenantHost: string,
): Record<string, string> {
  const headers: Record<string, string> = {};
  requestHeaders.forEach((value, name) => {
    if (!isStrippedRequestHeader(name)) {
      headers[name.toLowerCase()] = value;
    }
  });
  headers['host'] = tenantHost;
  return headers;
}

/**
 * Normalize one request for the tenant transport: `cache: "no-store"` is
 * stamped unconditionally (the ADR-021 contract — even though this
 * transport also bypasses every fetch cache by construction, the request
 * object itself must always carry the declaration).
 */
export function normalizeTenantRequest(
  input: Request | string | URL,
  init?: RequestInit,
): Request {
  const base = input instanceof Request ? input : new Request(input, init);
  return new Request(base, { cache: 'no-store' });
}

export interface TenantFetchOptions {
  /** Total deadline for connect + headers + body. Tests inject a short one. */
  timeoutMs?: number;
}

/**
 * A fetch-compatible function bound to one tenant Host, suitable for
 * injection into the api-client facade (`createApiClient({ fetch })`).
 */
export function createTenantFetch(
  tenantHost: string,
  options: TenantFetchOptions = {},
): (input: Request | string | URL, init?: RequestInit) => Promise<Response> {
  const timeoutMs = options.timeoutMs ?? SERVER_FETCH_TIMEOUT_MS;

  return async function tenantFetch(input, init) {
    const request = normalizeTenantRequest(input, init);
    const method = request.method.toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      throw new TypeError('tenant fetch is read-only: only GET and HEAD');
    }
    if (request.body !== null) {
      throw new TypeError('tenant fetch requests must not carry a body');
    }
    const url = new URL(request.url);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      throw new TypeError('tenant fetch supports only http(s) URLs');
    }
    const headers = wireHeaders(request.headers, tenantHost);

    return await new Promise<Response>((resolve, reject) => {
      const transport = url.protocol === 'https:' ? https : http;
      let settled = false;
      const fail = (reason: string): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        req.destroy();
        reject(new TypeError(`tenant fetch failed: ${reason}`));
      };
      const req = transport.request(url, { method, headers }, (res) => {
        const status = res.statusCode ?? 0;
        if (status < 200 || status > 599) {
          res.resume();
          fail(`unsupported status ${String(status)}`);
          return;
        }
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('error', () => fail('response stream error'));
        res.on('end', () => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          const responseHeaders = new Headers();
          for (let i = 0; i + 1 < res.rawHeaders.length; i += 2) {
            const name = res.rawHeaders[i] as string;
            const value = res.rawHeaders[i + 1] as string;
            if (!STRIPPED_RESPONSE_HEADERS.has(name.toLowerCase())) {
              responseHeaders.append(name, value);
            }
          }
          const bodyless =
            method === 'HEAD' ||
            status === 204 ||
            status === 205 ||
            status === 304;
          resolve(
            new Response(bodyless ? null : Buffer.concat(chunks), {
              status,
              headers: responseHeaders,
            }),
          );
        });
      });
      const timer = setTimeout(() => fail('timeout'), timeoutMs);
      req.on('error', () => fail('connection error'));
      req.end();
    });
  };
}
