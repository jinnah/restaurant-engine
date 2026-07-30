import { join } from 'node:path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  typedRoutes: true,
  // The shared renderer is consumed as raw TypeScript source with CSS
  // Modules (ADR-022 §2); Next compiles it like application code.
  transpilePackages: ['@restaurant-engine/storefront-renderer'],
  turbopack: {
    // Pin the monorepo root explicitly. Without this, Next infers the
    // workspace root by scanning upward for lockfiles and can select a
    // stray lockfile outside the repository (observed: a package-lock.json
    // in the user profile), which then breaks its swc dependency check.
    root: join(__dirname, '..', '..'),
  },
  async headers() {
    return [
      {
        // Storefront HTML, metadata routes, and error responses are
        // `no-store` (ADR-020 §12): publication replaces the projection in
        // place, and suspension must not be outlived by a cached page.
        // Deliberately excluded: `/_next/*` (hashed immutable build
        // assets keep the framework's long-lived caching) and `/api/*`
        // (the development forwarder passes the backend's own
        // centrally-assigned cache policy through untouched).
        source: '/((?!_next/|api/).*)',
        headers: [{ key: 'Cache-Control', value: 'no-store' }],
      },
    ];
  },
};

export default nextConfig;
