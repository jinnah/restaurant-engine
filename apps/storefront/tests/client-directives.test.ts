// @vitest-environment node

// The structural JavaScript budget (ADR-021): the storefront ships zero
// client components beyond the framework-required route error boundary.
// This scan is the budget's teeth — a new 'use client' directive anywhere
// in the application fails the suite until the allowlist (and ADR-021)
// are deliberately amended.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

const ALLOWED_CLIENT_FILES = ['app/error.tsx'];

function clientDirectiveFiles(root: string, dirs: string[]): string[] {
  const hits: string[] = [];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry.startsWith('.')) continue;
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) {
        walk(path);
      } else if (/\.(ts|tsx)$/.test(entry)) {
        const source = readFileSync(path, 'utf-8');
        if (/^\s*['"]use client['"]/.test(source)) {
          hits.push(path.slice(root.length + 1).replaceAll('\\', '/'));
        }
      }
    }
  };
  for (const dir of dirs) {
    walk(join(root, dir));
  }
  return hits.sort();
}

describe('client-component allowlist', () => {
  test("the only 'use client' file is the route error boundary", () => {
    const root = join(__dirname, '..');
    expect(clientDirectiveFiles(root, ['app', 'components', 'lib'])).toEqual(
      ALLOWED_CLIENT_FILES,
    );
  });
});
