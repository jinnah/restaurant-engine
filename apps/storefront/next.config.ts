import { join } from 'node:path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  typedRoutes: true,
  turbopack: {
    // Pin the monorepo root explicitly. Without this, Next infers the
    // workspace root by scanning upward for lockfiles and can select a
    // stray lockfile outside the repository (observed: a package-lock.json
    // in the user profile), which then breaks its swc dependency check.
    root: join(__dirname, '..', '..'),
  },
};

export default nextConfig;
