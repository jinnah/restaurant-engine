// Development-only same-origin API forwarding (ADR-021; POST for the
// public ordering surface added by ADR-026 D9). See the route handler
// `app/api/[...path]/route.ts` for the architectural rationale; the
// logic lives here so the real forwarding behavior is testable against
// a live local stub without importing a bracketed route path.

import { Buffer } from 'node:buffer';
import http from 'node:http';
import https from 'node:https';

import { resolveApiOrigin } from './api-origin';
import {
  createTenantFetch,
  SERVER_FETCH_TIMEOUT_MS,
  wireHeaders,
} from './tenant-fetch';

// Conditional request headers are forwarded so cached media revalidates
// (304) exactly as it would against the backend directly. Accept-Encoding
// is deliberately not forwarded: the transport buffers identity bodies.
const FORWARDED_REQUEST_HEADERS = ['accept', 'if-none-match'];

// POST (ADR-026 D9): the browser-context evidence travels verbatim —
// the backend's fail-closed check needs exactly what the browser sent
// (Sec-Fetch-Site, or the Origin/Referer fallbacks), and the forwarded
// Host equals the browser's origin host, so the self-origin branch
// behaves identically through the forwarder and in production.
const FORWARDED_POST_HEADERS = [
  'accept',
  'content-type',
  'origin',
  'referer',
  'sec-fetch-site',
  'sec-fetch-mode',
  'sec-fetch-dest',
];

// The one POST namespace the forwarder serves (ADR-026 D9): the public
// ordering surface. Everything else stays a refusal — the forwarder
// must never become a general write path to the admin or platform API.
const POST_PATH_PREFIX = '/api/v1/public/';

// Response headers that must not be copied onto the buffered Response
// (the tenant transport applies the same policy for GET/HEAD).
const STRIPPED_POST_RESPONSE_HEADERS = new Set([
  'connection',
  'keep-alive',
  'transfer-encoding',
  'te',
  'trailer',
  'upgrade',
  'proxy-authenticate',
  'proxy-authorization',
  'content-length',
  'set-cookie',
]);

function neutralResponse(status: number): Response {
  return new Response(null, {
    status,
    headers: { 'cache-control': 'no-store' },
  });
}

export function developmentProxyEnabled(
  env: Record<string, string | undefined> = process.env,
): boolean {
  return env['NODE_ENV'] !== 'production';
}

export async function forwardDevApiRequest(
  request: Request,
): Promise<Response> {
  if (!developmentProxyEnabled()) {
    return neutralResponse(404);
  }
  const host = request.headers.get('host');
  if (host === null || host === '') {
    return neutralResponse(404);
  }
  const incoming = new URL(request.url);
  const target = new URL(
    incoming.pathname + incoming.search,
    resolveApiOrigin(),
  );
  // Defense in depth: the route mount already scopes this handler to
  // /api/*, and URL construction normalizes dot segments — after which
  // the target must still sit inside the backend API namespace. Anything
  // else (however it got here) forwards nothing.
  if (!target.pathname.startsWith('/api/')) {
    return neutralResponse(404);
  }
  if (request.method.toUpperCase() === 'POST') {
    // ADR-026 D9: POST forwards only for the public ordering surface,
    // and never through the tenant transport — that primitive stays
    // read-only by design.
    if (!target.pathname.startsWith(POST_PATH_PREFIX)) {
      return neutralResponse(404);
    }
    return forwardPublicPost(request, target, host);
  }
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) {
      headers.set(name, value);
    }
  }
  const tenantFetch = createTenantFetch(host);
  try {
    return await tenantFetch(
      new Request(target, { method: request.method, headers }),
    );
  } catch {
    return neutralResponse(502);
  }
}

/**
 * The development-only POST leg (ADR-026 D9): body and browser-context
 * evidence forwarded verbatim, Host applied through the same sanitized
 * wire-header policy the tenant transport proves. Built directly on
 * `node:http(s)` for the same two load-bearing reasons as the tenant
 * transport: guaranteed Host control and structural immunity from the
 * framework fetch cache.
 */
async function forwardPublicPost(
  request: Request,
  target: URL,
  host: string,
): Promise<Response> {
  const forwarded = new Headers();
  for (const name of FORWARDED_POST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) {
      forwarded.set(name, value);
    }
  }
  const body = Buffer.from(await request.arrayBuffer());
  const headers = wireHeaders(forwarded, host);
  headers['content-length'] = String(body.byteLength);

  try {
    return await new Promise<Response>((resolve, reject) => {
      const transport = target.protocol === 'https:' ? https : http;
      let settled = false;
      const fail = (reason: string): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        req.destroy();
        reject(new Error(`dev post forward failed: ${reason}`));
      };
      const req = transport.request(
        target,
        { method: 'POST', headers },
        (res) => {
          const chunks: Buffer[] = [];
          res.on('data', (chunk: Buffer) => chunks.push(chunk));
          res.on('error', () => {
            fail('response stream error');
          });
          res.on('end', () => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            const responseHeaders = new Headers();
            for (let i = 0; i + 1 < res.rawHeaders.length; i += 2) {
              const name = res.rawHeaders[i] as string;
              const value = res.rawHeaders[i + 1] as string;
              if (!STRIPPED_POST_RESPONSE_HEADERS.has(name.toLowerCase())) {
                responseHeaders.append(name, value);
              }
            }
            resolve(
              new Response(Buffer.concat(chunks), {
                status: res.statusCode ?? 0,
                headers: responseHeaders,
              }),
            );
          });
        },
      );
      const timer = setTimeout(() => {
        fail('timeout');
      }, SERVER_FETCH_TIMEOUT_MS);
      req.on('error', () => {
        fail('connection error');
      });
      req.end(body);
    });
  } catch {
    return neutralResponse(502);
  }
}
