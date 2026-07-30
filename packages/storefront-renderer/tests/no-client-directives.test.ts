// @vitest-environment node

// The shared renderer is framework-neutral server-safe code (ADR-022 §2):
// no 'use client' directive may exist anywhere in the package, so
// everything it exports stays a server component in the storefront and
// adds zero client JavaScript. The allowlist is deliberately empty.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

function clientDirectiveFiles(root: string): string[] {
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
  walk(join(root, 'src'));
  return hits.sort();
}

describe('renderer package client-directive scan', () => {
  test("no file in the package carries 'use client'", () => {
    expect(clientDirectiveFiles(join(__dirname, '..'))).toEqual([]);
  });
});
