// Public-safe CI artifact preparation (M2F artifact policy, ADR-016).
//
// The repository is PUBLIC: anything uploaded from CI is downloadable
// by anyone with a GitHub account. Playwright traces record fill()
// arguments and request bodies (synthetic passwords, one-time tokens),
// failure screenshots can capture the one-time token reveal, and the
// HTML report embeds trace attachments — so none of those may ever be
// uploaded. The only approved public artifact is Playwright's
// `error-context.md` (an ARIA page snapshot), and even that can contain
// a rendered one-time token, so every candidate is secret-scanned and
// the whole upload fails closed on any hit.
//
// This script builds a FRESH sanitized directory (`e2e/ci-artifacts`)
// from exactly the approved files, validates the result, and exits
// nonzero — after deleting the directory — on any policy violation. It
// never prints a detected secret value, only the pattern name. Node
// built-ins only; injectable fs seam for deterministic tests.

import {
  copyFileSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
} from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ADMIN_PASSWORD } from './orchestrator.mjs';

export const APPROVED_BASENAME = 'error-context.md';

/** Thrown for every policy violation; message never carries a secret. */
export class ArtifactPolicyError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ArtifactPolicyError';
  }
}

/**
 * Known synthetic secrets and issued-token shapes. Matchers return only
 * a pattern NAME — the matched value is never surfaced anywhere.
 */
export const SECRET_PATTERNS = [
  {
    name: 'synthetic-admin-password',
    matches: (text) => text.includes(ADMIN_PASSWORD),
  },
  {
    name: 'synthetic-owner-password-family',
    matches: (text) => text.includes('e2e-only owner pw'),
  },
  {
    // Issued invitation/reset tokens are 256-bit URL-safe values
    // (43 base64url chars); session/CSRF values share the shape.
    name: 'issued-token-shaped-value',
    matches: (text) => /[A-Za-z0-9_-]{43,}/.test(text),
  },
];

export function scanForSecrets(text) {
  return SECRET_PATTERNS.filter((pattern) => pattern.matches(text)).map(
    (pattern) => pattern.name,
  );
}

/**
 * Walk `rootDir` collecting approved files. Any symlink anywhere in the
 * tree is a hard policy failure — a link could smuggle content from
 * outside the artifact root past the allowlist.
 */
export function collectApprovedFiles(rootDir) {
  const rootAbs = resolve(rootDir);
  const approved = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      const stats = lstatSync(path);
      if (stats.isSymbolicLink()) {
        throw new ArtifactPolicyError(
          `symlink in artifact tree: ${relative(rootAbs, path)}`,
        );
      }
      if (stats.isDirectory()) {
        walk(path);
        continue;
      }
      if (!stats.isFile() || entry !== APPROVED_BASENAME) {
        continue; // only the exact approved basename is ever selected
      }
      const rel = relative(rootAbs, path);
      if (rel.startsWith('..')) {
        throw new ArtifactPolicyError(`path escapes artifact root: ${rel}`);
      }
      approved.push(rel);
    }
  };
  walk(rootAbs);
  return approved.sort();
}

/**
 * The output directory must contain ONLY regular `error-context.md`
 * files, each of which passes the secret scan. Anything else — an
 * unexpected name, extension, or symlink — fails the whole upload.
 */
export function validateOutputDir(outputDir) {
  const outAbs = resolve(outputDir);
  const validated = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      const stats = lstatSync(path);
      if (stats.isSymbolicLink()) {
        throw new ArtifactPolicyError(
          `unexpected symlink in sanitized upload: ${relative(outAbs, path)}`,
        );
      }
      if (stats.isDirectory()) {
        walk(path);
        continue;
      }
      if (entry !== APPROVED_BASENAME) {
        throw new ArtifactPolicyError(
          `unexpected file in sanitized upload: ${relative(outAbs, path)}`,
        );
      }
      const hits = scanForSecrets(readFileSync(path, 'utf8'));
      if (hits.length > 0) {
        throw new ArtifactPolicyError(
          `secret-scan hit (${hits.join(', ')}) in ${relative(outAbs, path)}`,
        );
      }
      validated.push(relative(outAbs, path));
    }
  };
  walk(outAbs);
  return validated.sort();
}

/**
 * Build the sanitized upload directory. Returns the validated relative
 * paths; throws ArtifactPolicyError (after removing the output
 * directory) on any violation, so a failed preparation leaves nothing
 * uploadable behind.
 */
export function prepareCiArtifacts({ sourceDir, outputDir }) {
  rmSync(outputDir, { recursive: true, force: true });
  if (!existsSync(sourceDir)) {
    return []; // nothing failed with artifacts; nothing to upload
  }
  try {
    const approved = collectApprovedFiles(sourceDir);
    for (const rel of approved) {
      const from = join(sourceDir, rel);
      const hits = scanForSecrets(readFileSync(from, 'utf8'));
      if (hits.length > 0) {
        // Fail closed: one tainted candidate voids the whole upload.
        throw new ArtifactPolicyError(
          `secret-scan hit (${hits.join(', ')}) in ${rel}; ` +
            'no artifact will be uploaded',
        );
      }
      const to = join(outputDir, rel);
      mkdirSync(dirname(to), { recursive: true });
      copyFileSync(from, to);
    }
    if (approved.length === 0) {
      return [];
    }
    return validateOutputDir(outputDir);
  } catch (error) {
    rmSync(outputDir, { recursive: true, force: true });
    throw error;
  }
}

const isCliEntry =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isCliEntry) {
  const e2eDir = dirname(dirname(fileURLToPath(import.meta.url)));
  try {
    const files = prepareCiArtifacts({
      sourceDir: join(e2eDir, 'test-results'),
      outputDir: join(e2eDir, 'ci-artifacts'),
    });
    if (files.length === 0) {
      console.log('[ci-artifacts] nothing approved to upload');
    } else {
      console.log(
        `[ci-artifacts] approved ${files.length} file(s):\n` +
          files.map((file) => `  ${file}`).join('\n'),
      );
    }
  } catch (error) {
    console.error(`[ci-artifacts] ${error.message}`);
    console.error(
      '[ci-artifacts] failing closed: no artifact will be uploaded. ' +
        'Reproduce locally with `pnpm e2e` for full traces.',
    );
    process.exit(3);
  }
}
