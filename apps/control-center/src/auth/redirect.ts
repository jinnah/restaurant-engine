const FALLBACK = '/';
const MAX_LENGTH = 2048;

// Control characters, DEL, or any literal backslash (path confusion).
const FORBIDDEN_CHARS = /[\u0000-\u001f\u007f\\]/;
// Percent-encoded path separators, any case (%2f, %5c): rejected outright
// rather than trusting router/browser normalization (ADR-015).
const ENCODED_SEPARATOR = /%2f|%5c/i;

/**
 * Reduce an untrusted `next` value to a safe internal redirect target.
 *
 * Returns only a normalized internal `pathname + search`; fragments are
 * dropped (no control-center route consumes them). Anything suspicious
 * falls back to `/`: non-strings, over-length values, control characters,
 * backslashes, encoded path separators, absolute or scheme-relative
 * URLs, anything resolving outside this origin, login loops (including
 * dot-segment-normalized equivalents), and query parameters whose
 * decoded names contain `token` — tokens never travel in URLs.
 */
export function sanitizeNext(raw: unknown): string {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > MAX_LENGTH) {
    return FALLBACK;
  }
  if (FORBIDDEN_CHARS.test(raw) || ENCODED_SEPARATOR.test(raw)) {
    return FALLBACK;
  }
  if (!raw.startsWith('/') || raw.startsWith('//')) {
    return FALLBACK;
  }
  let url: URL;
  try {
    url = new URL(raw, window.location.origin);
  } catch {
    return FALLBACK;
  }
  if (url.origin !== window.location.origin) {
    return FALLBACK;
  }
  const path = url.pathname;
  if (path === '/login' || path.startsWith('/login/')) {
    return FALLBACK;
  }
  for (const key of url.searchParams.keys()) {
    if (key.toLowerCase().includes('token')) {
      return FALLBACK;
    }
  }
  return path + url.search;
}
