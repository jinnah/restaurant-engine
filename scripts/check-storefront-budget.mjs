// Storefront first-load JavaScript budget (M4D, ADR-021; island
// reporting added for M6C, ADR-026).
//
// TWO measurements, deliberately separate:
//
// 1. THE CEILING (unchanged ADR-021 method): for each public route, the
//    client JS files named by that route's build manifest
//    (`.next/server/app/<route>/build-manifest.json`, `rootMainFiles`
//    plus any `pages['/_app']` entries), summed as raw bytes on disk and
//    compared against the recorded budget. The budget number is defined
//    BY this method — the clean-baseline measurement at adoption plus
//    10% (measured 2026-07-29 on the pinned toolchain: 456,547 bytes,
//    ceiling 502,201). Raising it, or re-baselining it under a different
//    method, is a reviewed ADR-021 amendment, never a script edit.
//
// 2. THE ISLAND REPORT (M6C, no threshold — the ADR-024 §11 CSS
//    precedent: measure and report, reconsider on evidence): each
//    route's own client chunks from its RSC client-reference manifest
//    (`<route>_client-reference-manifest.js`, `entryJSFiles`, the same
//    entry chain the CSS measurement walks), minus the chunks the root
//    layout entry already delivers. Before M6C every route's marginal
//    set was empty; the ordering islands are the first page-specific
//    client JavaScript, and this figure is their true per-route cost.
//    M6C discovery, recorded in its close-out: `rootMainFiles` does NOT
//    name the app-router client-components chunk (~58 KB) that every
//    route has always loaded, so the ceiling figure under-measures the
//    real first load by that constant; a corrected-baseline ADR-021
//    amendment is the candidate fix, and until it is reviewed the
//    ceiling keeps its original recorded meaning.
//
// Manifests are consulted for *which* files a route loads — never for
// their (unstable) hashed names — and every path resolves relative to
// the app directory, so the check is machine-independent.

import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_DIR = join(
  fileURLToPath(new URL('.', import.meta.url)),
  '..',
  'apps',
  'storefront',
);

const ROUTES = ['page', 'menu/page', 'order/page', 'order/track/[token]/page'];
const BUDGET_BYTES = 502_201; // 456,547 measured baseline + 10%

let failed = false;

/** One entry's JS chunk list from the RSC client-reference manifest. */
function entryChunks(entryJSFiles, suffix) {
  const key = Object.keys(entryJSFiles).find((candidate) =>
    candidate.endsWith(suffix),
  );
  if (key === undefined) {
    return null;
  }
  return (entryJSFiles[key] ?? []).filter(
    (file) => typeof file === 'string' && file.endsWith('.js'),
  );
}

/** The route's own island chunks: page-entry chunks the layout entry
 *  does not already deliver. */
function islandChunks(route) {
  const path = join(
    APP_DIR,
    '.next',
    'server',
    'app',
    `${route}_client-reference-manifest.js`,
  );
  let source;
  try {
    source = readFileSync(path, 'utf-8');
  } catch {
    return null;
  }
  const marker = source.indexOf('__RSC_MANIFEST[');
  const assignment = marker === -1 ? -1 : source.indexOf('= {', marker);
  if (assignment === -1) {
    return null;
  }
  let manifest;
  try {
    manifest = JSON.parse(
      source
        .slice(assignment + 2)
        .trim()
        .replace(/;$/, ''),
    );
  } catch {
    return null;
  }
  const entryJSFiles = manifest.entryJSFiles;
  if (typeof entryJSFiles !== 'object' || entryJSFiles === null) {
    return null;
  }
  // The rendered chain for a route is its root layout plus its own page
  // (error entries deliver only on the error path — the CSS script's
  // documented exclusion, applied identically).
  const layout = entryChunks(entryJSFiles, '/app/layout');
  const page = entryChunks(entryJSFiles, `/app/${route}`);
  if (layout === null || page === null) {
    return null;
  }
  const layoutSet = new Set(layout);
  return page.filter((file) => !layoutSet.has(file));
}

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
  const shared = [
    ...(manifest.rootMainFiles ?? []),
    ...((manifest.pages ?? {})['/_app'] ?? []),
  ].filter((file) => file.endsWith('.js'));
  let total = 0;
  for (const file of new Set(shared)) {
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
      ` (budget ${String(BUDGET_BYTES)}, ${String(shared.length)} files)`,
  );

  // The island report (M6C): measured and reported, no threshold.
  const islands = islandChunks(route);
  if (islands === null) {
    console.error(
      `budget: FAIL ${route} - unreadable client-reference manifest`,
    );
    failed = true;
    continue;
  }
  let islandBytes = 0;
  for (const file of new Set(islands)) {
    try {
      islandBytes += statSync(join(APP_DIR, '.next', file)).size;
    } catch {
      console.error(`budget: FAIL ${route} - manifest names missing chunk`);
      failed = true;
    }
  }
  console.log(
    `budget: INFO ${route}  route-specific island JS ${String(islandBytes)}` +
      ` bytes (${String(islands.length)} chunks, reported — no threshold)`,
  );
}

process.exit(failed ? 1 : 0);
