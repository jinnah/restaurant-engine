// Storefront CSS weight measurement and report (M4G-B, ADR-024 §11).
//
// ADR-024 deliberately introduces **no CSS threshold**: inventing a
// blocking number before any measurement exists would be arbitrary. What
// it does require is that M4G-B *measure and report* per-variant CSS
// weight, so a threshold can later be reconsidered on evidence — as its
// own recorded decision, exactly as the ADR-021 JavaScript budget was.
//
// So this command never fails on SIZE. It does fail on MEASUREMENT
// INTEGRITY: a missing build, an unreadable or unexpected manifest, a
// route it cannot resolve, or a stylesheet the manifest names but that is
// not on disk. A measurement tool that silently reports zero is worse
// than no tool at all, so every one of those conditions is a non-zero
// exit with a specific message.
//
// Method: for each public route, Next's RSC manifest
// (`.next/server/app/<entry>/page_client-reference-manifest.js`) carries
// an `entryCSSFiles` map from entry module to the stylesheets that entry
// delivers. The route's delivered CSS is the union of its layout and its
// own page entry — deduplicated, because those two entries legitimately
// name the same shared chunks. Turbopack emits no `app-build-manifest`,
// which is why this manifest is the source (the same reason the
// JavaScript budget reads each route's `build-manifest.json`).

import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const APP_DIR = join(REPO_ROOT, 'apps', 'storefront');
const NEXT_DIR = join(APP_DIR, '.next');
const RENDERER_VARIANTS = join(
  REPO_ROOT,
  'packages',
  'storefront-renderer',
  'src',
  'variants',
);

const ROUTES = [
  { label: '/', entry: 'page' },
  { label: '/menu', entry: 'menu/page' },
];

// The registered design variants (ADR-024 §3). Reported individually
// because the ADR asks for per-variant weight, even though static
// imports make the delivered figure identical — that identity is itself
// the finding, and hiding it would misreport the result.
const VARIANTS = ['classic', 'editorial', 'express'];

const failures = [];

function fail(message) {
  failures.push(message);
  console.error(`css: FAIL ${message}`);
}

/** Parse `globalThis.__RSC_MANIFEST["/route"] = {…};` into its object. */
function readManifest(entry) {
  // The entry is part of the FILENAME, not a directory: `page` resolves
  // to `app/page_client-reference-manifest.js` and `menu/page` to
  // `app/menu/page_client-reference-manifest.js`.
  const relative = `${entry}_client-reference-manifest.js`;
  let source;
  try {
    source = readFileSync(join(NEXT_DIR, 'server', 'app', relative), 'utf-8');
  } catch {
    fail(
      `${entry}: no client-reference manifest at ` +
        `.next/server/app/${relative} (run the production build first)`,
    );
    return null;
  }
  const marker = source.indexOf('__RSC_MANIFEST[');
  const assignment = marker === -1 ? -1 : source.indexOf('= {', marker);
  if (assignment === -1) {
    fail(`${entry}: manifest has an unexpected shape (no RSC assignment)`);
    return null;
  }
  try {
    return JSON.parse(
      source
        .slice(assignment + 2)
        .trim()
        .replace(/;$/, ''),
    );
  } catch (error) {
    fail(`${entry}: manifest is not parseable JSON (${error.message})`);
    return null;
  }
}

/** The deduplicated stylesheets one route delivers, with their bytes. */
function deliveredCss(route) {
  const manifest = readManifest(route.entry);
  if (manifest === null) {
    return null;
  }
  const entryCSSFiles = manifest.entryCSSFiles;
  if (typeof entryCSSFiles !== 'object' || entryCSSFiles === null) {
    fail(`${route.label}: manifest carries no entryCSSFiles map`);
    return null;
  }
  // The rendered chain for a route is its root layout plus its own page.
  // Error and global-error entries are deliberately excluded: their CSS
  // is delivered only on the error path, not on this route's response.
  const wanted = [`/app/layout`, `/app/${route.entry}`];
  const paths = new Set();
  for (const suffix of wanted) {
    const key = Object.keys(entryCSSFiles).find((candidate) =>
      candidate.endsWith(suffix),
    );
    if (key === undefined) {
      fail(
        `${route.label}: cannot resolve the "${suffix}" entry in the manifest`,
      );
      return null;
    }
    for (const file of entryCSSFiles[key] ?? []) {
      if (typeof file?.path === 'string') {
        paths.add(file.path);
      }
    }
  }
  if (paths.size === 0) {
    fail(`${route.label}: the manifest names no stylesheet for this route`);
    return null;
  }
  let bytes = 0;
  for (const relative of paths) {
    try {
      bytes += statSync(join(NEXT_DIR, relative)).size;
    } catch {
      fail(`${route.label}: manifest names a missing stylesheet ${relative}`);
      return null;
    }
  }
  return { bytes, files: paths.size };
}

// ------------------------------------------------------- delivered bytes

console.log('css: delivered stylesheet bytes per public route');
const delivered = new Map();
for (const route of ROUTES) {
  const measured = deliveredCss(route);
  if (measured === null) {
    continue;
  }
  delivered.set(route.label, measured);
  for (const variant of VARIANTS) {
    console.log(
      `css: ROUTE ${route.label.padEnd(6)} variant ${variant.padEnd(9)}` +
        ` delivered ${String(measured.bytes)} bytes` +
        ` (${String(measured.files)} stylesheets)`,
    );
  }
}

if (delivered.size > 0) {
  console.log(
    'css: NOTE the delivered figure is identical across variants because ' +
      'the variant registry statically imports every layout arm, so all ' +
      'variant stylesheets bundle into the same chunk. No code splitting ' +
      'is attempted (ADR-024 §11).',
  );
}

// -------------------------------------------- authored, diagnostic only

console.log(
  'css: authored per-variant stylesheet bytes (DIAGNOSTIC - source ' +
    'weight, NOT delivered bytes)',
);
for (const variant of VARIANTS) {
  const path = join(RENDERER_VARIANTS, variant, `${variant}.module.css`);
  try {
    console.log(
      `css: AUTHORED ${variant.padEnd(9)} ${String(statSync(path).size)} bytes`,
    );
  } catch {
    fail(`authored stylesheet missing for the "${variant}" variant`);
  }
}

// No size threshold exists by decision (ADR-024 §11); only measurement
// integrity can fail this command.
if (failures.length > 0) {
  console.error(
    `css: measurement failed (${String(failures.length)} problem(s)); ` +
      'no size threshold is enforced, but an unmeasurable build is not a pass.',
  );
  process.exit(1);
}
console.log('css: measurement complete; no size threshold is enforced.');
