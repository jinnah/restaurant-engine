// Per-host robots policy (ADR-021). A host with a published storefront
// allows indexing and advertises its sitemap at the deterministic
// canonical origin; a host that resolves nothing publicly disallows
// everything (there is nothing to index, and the response stays neutral).
// A backend outage answers 503 so crawlers retry rather than record a
// policy that is not the tenant's.

import { canonicalOrigin } from '../../lib/canonical';
import {
  getPublishedStorefront,
  getRequestHost,
} from '../../lib/server/storefront-data';

export const dynamic = 'force-dynamic';

const HEADERS = {
  'content-type': 'text/plain; charset=utf-8',
  'cache-control': 'no-store',
};

export async function GET(): Promise<Response> {
  const result = await getPublishedStorefront();
  if (result.kind === 'unavailable') {
    return new Response(null, { status: 503, headers: HEADERS });
  }
  const host = await getRequestHost();
  const origin = host === null ? null : canonicalOrigin(host);
  if (result.kind === 'ok' && origin !== null) {
    return new Response(
      `User-agent: *\nAllow: /\n\nSitemap: ${origin}/sitemap.xml\n`,
      { headers: HEADERS },
    );
  }
  return new Response('User-agent: *\nDisallow: /\n', { headers: HEADERS });
}
