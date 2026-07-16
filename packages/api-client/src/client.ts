// Internal openapi-fetch wiring. Applications never import this module's
// underlying library types directly; the facade (health.ts) is the public
// surface and translates generator idioms in exactly one place.

import createClient, { type Client, type ClientOptions } from 'openapi-fetch';

import type { paths } from './generated/schema';

export interface ApiClientOptions {
  /** API origin, e.g. `http://127.0.0.1:8000`. Explicit — the package reads no ambient config. */
  baseUrl: string;
  /** Injectable fetch implementation (tests, server runtimes). Defaults to global fetch. */
  fetch?: ClientOptions['fetch'];
}

export function createInternalClient(options: ApiClientOptions): Client<paths> {
  return createClient<paths>({
    baseUrl: options.baseUrl,
    fetch: options.fetch,
    // The session is an HttpOnly cookie (ADR-010): every call sends
    // credentials so callers can never forget them. Same-origin
    // deployment is the contract (ADR-012), so this is not a CORS relaxation.
    credentials: 'include',
  });
}
