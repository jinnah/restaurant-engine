import { safeJsonLdSerialize } from '../lib/json-ld';

// The single audited JSON-LD component (ADR-021): the only permitted
// dangerouslySetInnerHTML in the storefront, fed exclusively by the
// escaping serializer (lib/json-ld). A permanent test scans the app for
// any other dangerouslySetInnerHTML occurrence, so this boundary cannot
// silently widen. Everything else renders through React escaping.
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: safeJsonLdSerialize(data) }}
    />
  );
}
