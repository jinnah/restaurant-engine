// Development-only same-origin API forwarding (ADR-021). See the route
// handler `app/api/[...path]/route.ts` for the architectural rationale;
// the logic lives here so the real forwarding behavior is testable against
// a live local stub without importing a bracketed route path.

import { resolveApiOrigin } from './api-origin';
import { createTenantFetch } from './tenant-fetch';

// Conditional request headers are forwarded so cached media revalidates
// (304) exactly as it would against the backend directly. Accept-Encoding
// is deliberately not forwarded: the transport buffers identity bodies.
const FORWARDED_REQUEST_HEADERS = ['accept', 'if-none-match'];

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
