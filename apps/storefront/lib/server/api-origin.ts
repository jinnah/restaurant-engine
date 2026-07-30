// Backend API origin resolution (server-only).
//
// One server-only environment variable, `STOREFRONT_API_ORIGIN`, read at
// request time — never at build time — so the zero-environment production
// build (docs/05) keeps passing while a production *runtime* without the
// variable fails closed on the first request instead of silently talking
// to a default. Development and test fall back to the documented local API
// (docs/05: uvicorn on 127.0.0.1:8000).
//
// The value must be a bare http(s) origin: no path, query, hash, or
// userinfo. Anything else is a configuration error in every environment.

const DEVELOPMENT_DEFAULT_ORIGIN = 'http://127.0.0.1:8000';

export function resolveApiOrigin(
  env: Record<string, string | undefined> = process.env,
): string {
  const raw = env['STOREFRONT_API_ORIGIN'];
  if (raw === undefined || raw === '') {
    if (env['NODE_ENV'] === 'production') {
      throw new Error(
        'STOREFRONT_API_ORIGIN must be set in production (bare http(s) origin)',
      );
    }
    return DEVELOPMENT_DEFAULT_ORIGIN;
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error('STOREFRONT_API_ORIGIN must be an absolute http(s) URL');
  }
  const bareOrigin =
    (url.protocol === 'http:' || url.protocol === 'https:') &&
    url.pathname === '/' &&
    url.search === '' &&
    url.hash === '' &&
    url.username === '' &&
    url.password === '' &&
    !raw.endsWith('?') &&
    !raw.endsWith('#');
  if (!bareOrigin) {
    throw new Error(
      'STOREFRONT_API_ORIGIN must be a bare http(s) origin with no path, query, hash, or userinfo',
    );
  }
  return url.origin;
}
