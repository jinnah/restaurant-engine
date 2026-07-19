// Deterministic coverage for the public-safe CI artifact policy: the
// sanitizer itself (real filesystem in a temp dir, node:test only) and
// a static policy regression over the workflow file.

import assert from 'node:assert/strict';
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { ADMIN_PASSWORD } from './orchestrator.mjs';
import {
  ArtifactPolicyError,
  prepareCiArtifacts,
  scanForSecrets,
  validateOutputDir,
} from './prepare-ci-artifacts.mjs';

const SCRIPTS_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = dirname(dirname(SCRIPTS_DIR));

function world() {
  const base = mkdtempSync(join(tmpdir(), 'e2e-artifacts-'));
  const sourceDir = join(base, 'test-results');
  const outputDir = join(base, 'ci-artifacts');
  const write = (rel, content) => {
    const path = join(sourceDir, rel);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  };
  const cleanup = () => {
    rmSync(base, { recursive: true, force: true });
  };
  return { base, sourceDir, outputDir, write, cleanup };
}

test('only error-context.md files are selected; traces and images never are', () => {
  const w = world();
  try {
    w.write('spec-a/error-context.md', 'clean context a');
    w.write('spec-a/trace.zip', 'ZIPBYTES');
    w.write('spec-a/test-failed-1.png', 'PNGBYTES');
    w.write('spec-b/nested/error-context.md', 'clean context b');
    w.write('spec-b/report.html', '<html>report</html>');

    const files = prepareCiArtifacts({
      sourceDir: w.sourceDir,
      outputDir: w.outputDir,
    });

    assert.deepEqual(files.length, 2);
    assert.ok(files.every((file) => file.endsWith('error-context.md')));
    // The sanitized tree holds exactly the approved copies.
    assert.equal(
      readFileSync(join(w.outputDir, files[0]), 'utf8'),
      'clean context a',
    );
    assert.deepEqual(validateOutputDir(w.outputDir), files);
  } finally {
    w.cleanup();
  }
});

test('a missing source directory approves nothing and creates nothing', () => {
  const w = world();
  try {
    const files = prepareCiArtifacts({
      sourceDir: join(w.base, 'does-not-exist'),
      outputDir: w.outputDir,
    });
    assert.deepEqual(files, []);
  } finally {
    w.cleanup();
  }
});

test('an injected synthetic password fails closed without printing it', () => {
  const w = world();
  try {
    w.write('spec/error-context.md', `snapshot with ${ADMIN_PASSWORD} inside`);
    let caught = null;
    try {
      prepareCiArtifacts({ sourceDir: w.sourceDir, outputDir: w.outputDir });
    } catch (error) {
      caught = error;
    }
    assert.ok(caught instanceof ArtifactPolicyError);
    assert.match(caught.message, /secret-scan hit/);
    assert.ok(
      !caught.message.includes(ADMIN_PASSWORD),
      'the detected secret value must never be printed',
    );
    // Fail-closed: the upload directory was removed.
    assert.throws(() => validateOutputDir(w.outputDir));
  } finally {
    w.cleanup();
  }
});

test('an issued-token-shaped value is rejected', () => {
  const tokenish = 'A'.repeat(20) + 'b-c_' + 'D'.repeat(20); // 44 urlsafe chars
  assert.deepEqual(scanForSecrets(`text ${tokenish} text`), [
    'issued-token-shaped-value',
  ]);
  // Ordinary snapshot content (UUIDs, paths, prose) stays clean.
  assert.deepEqual(
    scanForSecrets(
      'link "/platform/businesses/5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001" ' +
        'heading "E2E onb Bistro" text: owner-onb@e2e.example',
    ),
    [],
  );
});

test('an unexpected file smuggled into the sanitized directory is rejected', () => {
  const w = world();
  try {
    mkdirSync(w.outputDir, { recursive: true });
    writeFileSync(join(w.outputDir, 'error-context.md'), 'clean');
    writeFileSync(join(w.outputDir, 'trace.zip'), 'ZIPBYTES');
    assert.throws(
      () => validateOutputDir(w.outputDir),
      /unexpected file in sanitized upload: trace\.zip/,
    );
  } finally {
    w.cleanup();
  }
});

test('a symlink anywhere in the tree is a hard policy failure', (t) => {
  const w = world();
  try {
    w.write('spec/error-context.md', 'clean');
    try {
      symlinkSync(join(w.base, 'outside.md'), join(w.sourceDir, 'link.md'));
    } catch {
      t.skip('symlink creation not permitted on this system');
      return;
    }
    assert.throws(
      () =>
        prepareCiArtifacts({ sourceDir: w.sourceDir, outputDir: w.outputDir }),
      /symlink in artifact tree/,
    );
  } finally {
    w.cleanup();
  }
});

// ---- Static workflow policy: the public repository must never upload
// traces, reports, or broad artifact directories again.

test('ci.yml uploads only the sanitized directory with bounded retention', () => {
  const ciYml = readFileSync(
    join(REPO_ROOT, '.github', 'workflows', 'ci.yml'),
    'utf8',
  );

  // The sensitive trees may not be referenced by the workflow at all
  // (prose may explain WHY traces are banned; paths may not name them).
  assert.ok(!ciYml.includes('playwright-report'), 'playwright-report banned');
  assert.ok(!ciYml.includes('test-results'), 'test-results banned');

  // Exactly one upload path: the sanitized directory, failure-only,
  // bounded retention, tolerant of an empty approved set. No trace,
  // report, zip, or video glob can therefore ever match.
  const uploadPaths = [...ciYml.matchAll(/^\s+path:\s*(.+)$/gm)].map((match) =>
    match[1].trim(),
  );
  assert.deepEqual(uploadPaths, ['e2e/ci-artifacts']);
  assert.ok(
    uploadPaths.every((path) => !/trace|report|zip|video|webm|png/i.test(path)),
    'sensitive globs banned from upload paths',
  );
  assert.match(ciYml, /retention-days: 7\b/);
  assert.match(ciYml, /if-no-files-found: ignore/);
  assert.match(ciYml, /prepare-ci-artifacts\.mjs/);
  const retentions = [...ciYml.matchAll(/retention-days:\s*(\d+)/g)].map(
    (match) => Number(match[1]),
  );
  assert.ok(retentions.every((days) => days <= 7));
});
