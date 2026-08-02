// Development-only same-origin API forwarder (ADR-021).
//
// In production the reverse proxy serves `/api/*` on the tenant origin
// directly (ADR-013's same-origin contract), so this route is disabled
// there and answers a neutral 404. In development the storefront dev
// server *is* the tenant origin (`{slug}.localhost:3000`), and the
// relative media URLs inside the public projection must resolve on it —
// so GET/HEAD requests under `/api/` are forwarded to the configured API
// origin through the tenant transport, which preserves the browser's
// original Host verbatim. Host preservation is the entire point: the
// backend resolves the tenant from it (ADR-013), and a forwarder that
// rewrote the Host would resolve no tenant at all.
//
// GET, HEAD, and — from M6C (ADR-026 D9) — POST are exported; every
// other method is a framework 405. POST forwards only for
// `/api/v1/public/` paths (the ordering surface's placement and
// cancellation), with the browser-context headers preserved verbatim,
// and the whole forwarder stays production-disabled — in production the
// reverse proxy serves the API same-origin and this route never runs.
// The destination is always the fixed API origin — the request
// influences the path and headers, never the target host — so the
// forwarder cannot be steered elsewhere. The forwarding logic (and its
// live-stub tests) live in `lib/server/dev-api-proxy.ts`.

import { forwardDevApiRequest } from '../../../lib/server/dev-api-proxy';

export const dynamic = 'force-dynamic';

export function GET(request: Request): Promise<Response> {
  return forwardDevApiRequest(request);
}

export function HEAD(request: Request): Promise<Response> {
  return forwardDevApiRequest(request);
}

export function POST(request: Request): Promise<Response> {
  return forwardDevApiRequest(request);
}
