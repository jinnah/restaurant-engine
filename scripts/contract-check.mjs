// Worktree-independent contract drift check (ADR-009).
//
// Generates the OpenAPI document and the TypeScript schema into a temporary
// directory using the identical pipeline as `pnpm generate:client`, then
// byte-compares the results against the two committed artifacts. The
// repository is never modified, so the check works with unrelated local
// changes present. Any unexpected generator output fails the check. The
// temporary directory is always removed.

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const packageDir = path.join(repoRoot, 'packages', 'api-client');

const EXPECTED_FILES = ['openapi.json', 'schema.ts'];
const committedPaths = {
  'openapi.json': path.join(packageDir, 'openapi.json'),
  'schema.ts': path.join(packageDir, 'src', 'generated', 'schema.ts'),
};

function run(command, args) {
  const result = spawnSync(command, args, { cwd: repoRoot, stdio: 'inherit' });
  if (result.error) {
    console.error(
      `contract check: failed to run ${command}: ${result.error.message}`,
    );
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(
      `contract check: ${command} ${args.join(' ')} exited with ${result.status}`,
    );
    process.exit(result.status ?? 1);
  }
}

const tmpDir = fs.mkdtempSync(
  path.join(os.tmpdir(), 'restaurant-engine-contract-'),
);
const drifted = [];
let unexpected = null;

try {
  run('uv', [
    'run',
    '--directory',
    'backend',
    'python',
    '-m',
    'scripts.export_openapi',
    path.join(tmpDir, 'openapi.json'),
  ]);
  run(process.execPath, [
    path.join(packageDir, 'scripts', 'generate.mjs'),
    path.join(tmpDir, 'openapi.json'),
    path.join(tmpDir, 'schema.ts'),
  ]);

  const produced = fs.readdirSync(tmpDir).sort();
  if (JSON.stringify(produced) !== JSON.stringify(EXPECTED_FILES)) {
    unexpected = produced;
  }

  for (const name of EXPECTED_FILES) {
    const freshPath = path.join(tmpDir, name);
    const committedPath = committedPaths[name];
    const fresh = fs.existsSync(freshPath) ? fs.readFileSync(freshPath) : null;
    const committed = fs.existsSync(committedPath)
      ? fs.readFileSync(committedPath)
      : null;
    if (fresh === null || committed === null || !fresh.equals(committed)) {
      drifted.push(path.relative(repoRoot, committedPath));
    }
  }
} finally {
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

if (unexpected !== null) {
  console.error(
    `contract check: unexpected generator output [${unexpected.join(', ')}]; ` +
      `expected exactly [${EXPECTED_FILES.join(', ')}]`,
  );
}
for (const artifact of drifted) {
  console.error(`contract check: DRIFT in ${artifact}`);
}
if (unexpected !== null || drifted.length > 0) {
  console.error(
    'contract check: run `corepack pnpm generate:client` from the repository root ' +
      'and commit both regenerated artifacts.',
  );
  process.exit(1);
}
console.log(
  'contract check: committed OpenAPI contract and generated client are current.',
);
