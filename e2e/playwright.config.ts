import { defineConfig, devices } from '@playwright/test';

// The orchestrator (`pnpm e2e`) owns the entire lifecycle: ports,
// database, seeding, servers, and cleanup. A bare `playwright test`
// would run against whatever happens to be listening — or nothing —
// so it refuses without the orchestrator's sentinel.
if (process.env['E2E_ORCHESTRATED'] !== '1') {
  throw new Error(
    'The E2E suite must run through its orchestrator: use `pnpm e2e` from ' +
      'the repository root (append a spec path or --grep to select tests). ' +
      'It provisions the isolated database and servers and guarantees ' +
      'cleanup; a bare playwright invocation cannot.',
  );
}

export default defineConfig({
  testDir: './tests',
  // Serial and deterministic (ADR-016): one worker, no cross-file
  // parallelism, zero retries — a flake is a bug, not a reroll. Specs
  // stay order-independent regardless (own namespaces, own fixtures).
  workers: 1,
  fullyParallel: false,
  retries: 0,
  forbidOnly: true,
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:5273',
    // Failure-only artifacts; synthetic credentials only, and the
    // database they belong to is dropped after every run — the report
    // directory is still treated as a sensitive test artifact.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
