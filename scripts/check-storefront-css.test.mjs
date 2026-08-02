// Regression coverage for the CSS weight measurement (M4G-B, ADR-024
// §11), in the repository's existing style: `node:test`, no dependency,
// deterministic fixtures, no real processes or servers.
//
// What this suite protects is **measurement integrity**, not size. The
// command deliberately enforces no threshold, so the only way it can
// mislead is by reporting a number that is wrong or absent — a missing
// build, an unreadable manifest, a route it silently skipped, an asset it
// silently ignored, or a shared chunk counted twice. Each of those is
// pinned below with an exact exit status.
//
// Every case runs against a **disposable fixture under the OS temp
// directory**: the script resolves its paths from its own location, so a
// byte-identical copy inside the fixture measures the fixture's tree. The
// repository's real production build is never read, written, or required
// — these tests pass on a clean checkout with no `.next` present.

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, test } from 'node:test';

const SCRIPT = fileURLToPath(
  new URL('./check-storefront-css.mjs', import.meta.url),
);
const REPO_ROOT = dirname(dirname(SCRIPT));
const VARIANTS = ['classic', 'editorial', 'express'];

/** Every fixture root this run created, for the cleanup assertion. */
const created = [];

/**
 * The manifest shape Next emits, with DELIBERATE duplication: the layout
 * names `a.css` twice and the page names both chunks again, so five raw
 * references must collapse to two unique assets.
 */
function defaultManifests() {
  return {
    page: {
      '[project]/apps/storefront/app/layout': [
        'static/chunks/a.css',
        'static/chunks/a.css',
        'static/chunks/b.css',
      ],
      // Deliberately present and deliberately ignored: error CSS is
      // delivered on the error path, not on this route's response.
      '[project]/apps/storefront/app/error': ['static/chunks/never.css'],
      '[project]/apps/storefront/app/page': [
        'static/chunks/a.css',
        'static/chunks/b.css',
      ],
    },
    'menu/page': {
      '[project]/apps/storefront/app/layout': [
        'static/chunks/a.css',
        'static/chunks/b.css',
      ],
      '[project]/apps/storefront/app/menu/page': [
        'static/chunks/b.css',
        'static/chunks/a.css',
      ],
    },
    // The M6C ordering routes (ADR-026) measure exactly like the content
    // routes; the dynamic tracking segment keeps its bracketed name.
    'order/page': {
      '[project]/apps/storefront/app/layout': [
        'static/chunks/a.css',
        'static/chunks/b.css',
      ],
      '[project]/apps/storefront/app/order/page': [
        'static/chunks/a.css',
        'static/chunks/b.css',
      ],
    },
    'order/track/[token]/page': {
      '[project]/apps/storefront/app/layout': [
        'static/chunks/a.css',
        'static/chunks/b.css',
      ],
      '[project]/apps/storefront/app/order/track/[token]/page': [
        'static/chunks/a.css',
        'static/chunks/b.css',
      ],
    },
  };
}

function writeManifest(root, entry, body) {
  const dir = join(root, 'apps', 'storefront', '.next', 'server', 'app');
  const target = entry.includes('/')
    ? join(dir, entry.slice(0, entry.lastIndexOf('/')))
    : dir;
  mkdirSync(target, { recursive: true });
  const name = `${entry.slice(entry.lastIndexOf('/') + 1)}_client-reference-manifest.js`;
  const source =
    typeof body === 'string'
      ? body
      : `globalThis.__RSC_MANIFEST = globalThis.__RSC_MANIFEST || {};\n` +
        `globalThis.__RSC_MANIFEST[${JSON.stringify(`/${entry}`)}] = ` +
        `${JSON.stringify({
          entryCSSFiles: Object.fromEntries(
            Object.entries(body).map(([key, paths]) => [
              key,
              paths.map((path) => ({ path, inlined: false })),
            ]),
          ),
        })};\n`;
  writeFileSync(join(target, name), source);
}

function makeFixture({
  manifests = defaultManifests(),
  chunks = { 'a.css': 1000, 'b.css': 500 },
  variants = VARIANTS,
  build = true,
} = {}) {
  const root = mkdtempSync(join(tmpdir(), 'storefront-css-'));
  created.push(root);
  // The fixture must live outside the repository, so a test can never
  // read or disturb the real production build.
  assert.ok(root.startsWith(tmpdir()), 'fixture must live under the temp dir');
  assert.ok(!root.startsWith(REPO_ROOT), 'fixture must be outside the repo');

  mkdirSync(join(root, 'scripts'), { recursive: true });
  copyFileSync(SCRIPT, join(root, 'scripts', 'check-storefront-css.mjs'));
  for (const variant of variants) {
    const dir = join(
      root,
      'packages',
      'storefront-renderer',
      'src',
      'variants',
      variant,
    );
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, `${variant}.module.css`), 'z'.repeat(64));
  }
  if (build) {
    const chunkDir = join(
      root,
      'apps',
      'storefront',
      '.next',
      'static',
      'chunks',
    );
    mkdirSync(chunkDir, { recursive: true });
    for (const [name, size] of Object.entries(chunks)) {
      writeFileSync(join(chunkDir, name), 'x'.repeat(size));
    }
    for (const [entry, body] of Object.entries(manifests)) {
      writeManifest(root, entry, body);
    }
  }
  return root;
}

function run(root) {
  const result = spawnSync(
    process.execPath,
    [join(root, 'scripts', 'check-storefront-css.mjs')],
    { encoding: 'utf-8' },
  );
  return {
    status: result.status,
    stdout: result.stdout ?? '',
    stderr: result.stderr ?? '',
  };
}

/** Create a fixture, run the command against it, and always clean up. */
function measure(options) {
  const root = makeFixture(options);
  try {
    return run(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

/** The `ROUTE … variant … delivered N bytes` rows, parsed. */
function deliveredRows(stdout) {
  return [
    ...stdout.matchAll(
      /^css: ROUTE (\S+)\s+variant (\S+)\s+delivered (\d+) bytes/gm,
    ),
  ].map((match) => ({
    route: match[1],
    variant: match[2],
    bytes: Number(match[3]),
  }));
}

// ------------------------------------------------- measurement integrity

test('absent production build output exits nonzero', () => {
  const result = measure({ build: false });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /no client-reference manifest/);
});

test('a malformed manifest exits nonzero', () => {
  const manifests = defaultManifests();
  manifests.page = 'globalThis.__RSC_MANIFEST["/page"] = {oops;\n';
  const result = measure({ manifests });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /not parseable JSON/);
});

test('an unexpected manifest shape exits nonzero', () => {
  const manifests = defaultManifests();
  manifests.page = '// no RSC assignment here at all\n';
  const result = measure({ manifests });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /unexpected shape/);
});

test('a manifest without an entryCSSFiles map exits nonzero', () => {
  const manifests = defaultManifests();
  manifests.page =
    'globalThis.__RSC_MANIFEST["/page"] = {"clientModules":{}};\n';
  const result = measure({ manifests });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /no entryCSSFiles map/);
});

test('an unresolved "/" exits nonzero', () => {
  const manifests = defaultManifests();
  delete manifests.page['[project]/apps/storefront/app/page'];
  const result = measure({ manifests });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /\/: cannot resolve the "\/app\/page" entry/);
});

test('an unresolved "/menu" exits nonzero', () => {
  const manifests = defaultManifests();
  delete manifests['menu/page']['[project]/apps/storefront/app/menu/page'];
  const result = measure({ manifests });
  assert.equal(result.status, 1);
  assert.match(
    result.stderr,
    /\/menu: cannot resolve the "\/app\/menu\/page" entry/,
  );
});

test('an unresolved layout entry exits nonzero', () => {
  const manifests = defaultManifests();
  delete manifests.page['[project]/apps/storefront/app/layout'];
  const result = measure({ manifests });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /cannot resolve the "\/app\/layout" entry/);
});

test('a referenced but missing CSS asset exits nonzero', () => {
  const result = measure({ chunks: { 'a.css': 1000 } });
  assert.equal(result.status, 1);
  assert.match(
    result.stderr,
    /names a missing stylesheet static\/chunks\/b\.css/,
  );
});

// ------------------------------------------------------ successful output

test('duplicate CSS references are counted exactly once', () => {
  // Five raw references across the layout and page entries resolve to two
  // unique assets: 1000 + 500. Counting references rather than assets
  // would report 4000.
  const result = measure();
  assert.equal(result.status, 0);
  for (const row of deliveredRows(result.stdout)) {
    assert.equal(row.bytes, 1500, `${row.route}/${row.variant}`);
  }
  assert.match(result.stdout, /\(2 stylesheets\)/);
  // The error entry's stylesheet is excluded, not merely absent by luck.
  assert.doesNotMatch(result.stdout, /never\.css/);
});

test('exactly one delivered row per route and variant', () => {
  const result = measure();
  assert.equal(result.status, 0);
  const rows = deliveredRows(result.stdout);
  assert.equal(rows.length, 12);
  const seen = new Map();
  for (const row of rows) {
    const key = `${row.route}|${row.variant}`;
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }
  for (const route of ['/', '/menu', '/order', '/order/track/[token]']) {
    for (const variant of VARIANTS) {
      assert.equal(
        seen.get(`${route}|${variant}`),
        1,
        `expected exactly one row for ${route} x ${variant}`,
      );
    }
  }
});

test('authored per-variant bytes are labelled diagnostic, not delivered', () => {
  const result = measure();
  assert.equal(result.status, 0);
  assert.match(
    result.stdout,
    /authored per-variant stylesheet bytes \(DIAGNOSTIC - source weight, NOT delivered bytes\)/,
  );
  for (const variant of VARIANTS) {
    assert.match(
      result.stdout,
      new RegExp(`^css: AUTHORED ${variant}\\s+64 bytes`, 'm'),
    );
  }
  // The diagnostic figure is reported separately from the delivered one
  // and must never be presented as delivered bytes.
  assert.doesNotMatch(result.stdout, /^css: ROUTE .*64 bytes/m);
});

test('a very large stylesheet still succeeds: no blocking size threshold', () => {
  const result = measure({ chunks: { 'a.css': 5_000_000, 'b.css': 500 } });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /delivered 5000500 bytes/);
  assert.match(result.stdout, /no size threshold is enforced/);
});

// ------------------------------------------------------------- hygiene

test('the suite never reads the repository production build', () => {
  // The script under test resolves every path from its own location, so
  // measuring a fixture copy cannot reach the repository's `.next`. This
  // pins that property rather than trusting it.
  const root = makeFixture();
  try {
    assert.ok(!root.startsWith(REPO_ROOT));
    const result = run(root);
    assert.equal(result.status, 0);
    assert.doesNotMatch(result.stdout + result.stderr, /apps[\\/]storefront/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

after(() => {
  const survivors = created.filter((root) => existsSync(root));
  for (const root of survivors) {
    rmSync(root, { recursive: true, force: true });
  }
  assert.deepEqual(survivors, [], 'every temporary fixture must be removed');
});
