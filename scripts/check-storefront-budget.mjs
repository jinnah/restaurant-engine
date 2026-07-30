// Storefront first-load JavaScript budget (M4D, ADR-021).
//
// Measurement: for each public route, the client JS files named by that
// route's build manifest (`.next/server/app/<route>/build-manifest.json`,
// `rootMainFiles` plus any `pages['/_app']` entries), summed as raw bytes
// on disk. The manifest is consulted for *which* files a route loads —
// never for their (unstable) hashed names — and every path is resolved
// relative to the app directory, so the check is machine-independent.
//
// Budget: the clean-baseline measurement at adoption plus 10%. Baseline
// measured 2026-07-29 on the pinned toolchain (Next 16.2.10, React
// 19.2.7, Turbopack production build): 456,547 bytes per route — entirely
// shared framework runtime; both public routes ship zero page-specific
// client JavaScript (the ADR-021 structural budget). A failure here means
// a client component, dependency, or framework change grew the first
// load; raise the budget only through a reviewed ADR-021 amendment.

import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_DIR = join(
  fileURLToPath(new URL('.', import.meta.url)),
  '..',
  'apps',
  'storefront',
);

const ROUTES = ['page', 'menu/page'];
const BUDGET_BYTES = 502_201; // 456,547 measured baseline + 10%

let failed = false;

for (const route of ROUTES) {
  const manifestPath = join(
    APP_DIR,
    '.next',
    'server',
    'app',
    route,
    'build-manifest.json',
  );
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
  } catch {
    console.error(
      `budget: FAIL ${route} - missing build manifest (run the production build first)`,
    );
    failed = true;
    continue;
  }
  const files = [
    ...(manifest.rootMainFiles ?? []),
    ...((manifest.pages ?? {})['/_app'] ?? []),
  ].filter((file) => file.endsWith('.js'));
  let total = 0;
  for (const file of new Set(files)) {
    try {
      total += statSync(join(APP_DIR, '.next', file)).size;
    } catch {
      console.error(`budget: FAIL ${route} - manifest names missing file`);
      failed = true;
    }
  }
  const verdict = total <= BUDGET_BYTES ? 'OK  ' : 'FAIL';
  if (total > BUDGET_BYTES) {
    failed = true;
  }
  console.log(
    `budget: ${verdict} ${route}  first-load JS ${String(total)} bytes` +
      ` (budget ${String(BUDGET_BYTES)}, ${String(files.length)} files)`,
  );
}

process.exit(failed ? 1 : 0);
