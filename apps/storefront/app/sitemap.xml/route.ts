// Per-host sitemap (ADR-021): exactly the routes that exist — `/` and
// `/menu` — as absolute URLs on the deterministic canonical origin
// (ADR-020 §1: the sitemap emits only routes that exist; no /order until
// M6). A host without a published storefront has no public site and no
// sitemap: the same neutral 404 as its pages. A backend outage is 503.

import { canonicalOrigin } from '../../lib/canonical';
import {
  getPublishedStorefront,
  getRequestHost,
} from '../../lib/server/storefront-data';

export const dynamic = 'force-dynamic';

const HEADERS = {
  'content-type': 'application/xml; charset=utf-8',
  'cache-control': 'no-store',
};

export async function GET(): Promise<Response> {
  const result = await getPublishedStorefront();
  if (result.kind === 'unavailable') {
    return new Response(null, { status: 503, headers: HEADERS });
  }
  const host = await getRequestHost();
  const origin = host === null ? null : canonicalOrigin(host);
  if (result.kind !== 'ok' || origin === null) {
    return new Response(null, { status: 404, headers: HEADERS });
  }
  const urls = ['/', '/menu']
    .map((path) => `  <url><loc>${origin}${path}</loc></url>`)
    .join('\n');
  const body = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
  return new Response(body, { headers: HEADERS });
}
