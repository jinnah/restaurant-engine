/**
 * Per-spec namespaces (ADR-016): every spec owns a fixed, distinct
 * slug/email family inside a database that is recreated fresh each run,
 * so specs are collision-free by construction, order-independent, and
 * individually runnable. No spec may reference another spec's names.
 *
 * Extended in M3F (ADR-019): a spec may own **several** keys when its
 * subject genuinely needs more than one business — cross-business
 * isolation cannot be demonstrated with one tenant. The invariant is
 * unchanged and is the one that matters: every key belongs to exactly
 * one spec, and no spec ever names another spec's.
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

/** The backend port the orchestrator started; public hosts resolve there. */
const PUBLIC_PORT = process.env['E2E_PUBLIC_PORT'] ?? '8100';

/**
 * The public origin of one tenant: `http://{slug}.localhost:{backend}`.
 *
 * A direct subdomain of the platform base domain (`localhost` in
 * development) is what `resolve_public_business` reads, and it reads the
 * **Host** — never a path, query, header, or cookie. Two consequences
 * shape every public assertion in this suite:
 *
 * 1. It cannot go through the UI origin. The Vite proxy forwards with
 *    `changeOrigin: false`, so a proxied `/api/...` request arrives with
 *    `Host: localhost:5273`, which is not one label above the base domain
 *    and therefore resolves to no tenant at all.
 * 2. It must be reached by **browser navigation**, never by Playwright's
 *    `request` fixture. `APIRequestContext` runs in the Node driver and
 *    uses the operating system resolver, and Windows does not resolve
 *    `*.localhost` (verified: ENOTFOUND). Chromium resolves the
 *    `.localhost` TLD to loopback itself, per RFC 6761, on both
 *    platforms — so `page.goto` works everywhere and `page.request`
 *    would pass on Linux CI and fail on a Windows machine.
 */
export function publicOrigin(slug: string): string {
  return `http://${slug}.localhost:${PUBLIC_PORT}`;
}

/**
 * The platform apex the tenant hosts sit under. It is a recognized host
 * but never a tenant — zero labels above the base domain — so it is the
 * honest control for "a valid host that resolves to no business".
 */
export const APEX_ORIGIN = `http://localhost:${PUBLIC_PORT}`;
