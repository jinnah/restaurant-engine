// Deterministic canonical-origin policy (ADR-021).
//
// The canonical origin is derived from the validated incoming Host — the
// same value the backend resolved the tenant from — under a fixed scheme
// rule: `http` only for the local development host family (`localhost`,
// `*.localhost`, loopback literals), `https` for every other host. No
// forwarded header is ever consulted (`X-Forwarded-Proto` is untrusted
// client input until the M8 proxy trust decision), and a legitimate
// development port is preserved. A host that does not look like a plain
// DNS host yields no canonical at all.

const HOST_SHAPE = /^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:\d{1,5})?$/;

export function canonicalOrigin(host: string): string | null {
  const normalized = host.toLowerCase();
  if (!HOST_SHAPE.test(normalized)) {
    return null;
  }
  const name = normalized.split(':')[0] ?? '';
  const local =
    name === 'localhost' || name.endsWith('.localhost') || name === '127.0.0.1';
  return `${local ? 'http' : 'https'}://${normalized}`;
}
