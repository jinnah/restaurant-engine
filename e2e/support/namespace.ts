/**
 * Per-spec namespaces (ADR-016): every spec owns a fixed, distinct
 * slug/email family inside a database that is recreated fresh each run,
 * so specs are collision-free by construction, order-independent, and
 * individually runnable. No spec may reference another spec's names.
 */
export interface SpecNamespace {
  slug: string;
  businessName: string;
  ownerEmail: string;
  ownerName: string;
  ownerPassword: string;
}

export function specNamespace(key: string): SpecNamespace {
  return {
    slug: `e2e-${key}`,
    businessName: `E2E ${key} Bistro`,
    ownerEmail: `owner-${key}@e2e.example`,
    ownerName: `E2E ${key} Owner`,
    // Synthetic, E2E-only; lives only in the disposable e2e database.
    ownerPassword: `e2e-only owner pw ${key} 9152!`,
  };
}

/** The globally seeded platform administrator (orchestrator-provided). */
export const ADMIN = {
  email: process.env['E2E_ADMIN_EMAIL'] ?? '',
  password: process.env['E2E_ADMIN_PASSWORD'] ?? '',
};

export const ORIGIN = process.env['E2E_BASE_URL'] ?? 'http://localhost:5273';
