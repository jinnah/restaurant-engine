import { createApiClient, type ApiClient } from '@restaurant-engine/api-client';

// Origin-relative base URL: every request is `/api/...` under the page
// origin. The Vite dev proxy and the production reverse proxy both serve
// the API on the same origin, so the session cookie is always first-party
// and no CORS surface exists (ADR-015).
export function createBrowserClient(): ApiClient {
  return createApiClient({ baseUrl: '' });
}
