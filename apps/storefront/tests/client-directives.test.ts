// @vitest-environment node

// The structural JavaScript budget (ADR-021, amended by ADR-026 M6C):
// the storefront ships exactly the framework-required route error
// boundary plus the five named ordering islands (§12.1's allowed
// islands — the cart affordances, the modifier dialog, the checkout
// form, and the tracker). This scan is the budget's teeth — a new
// 'use client' directive anywhere else fails the suite until the
// allowlist (and the ADR) are deliberately amended.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

const ALLOWED_CLIENT_FILES = [
  'app/error.tsx',
  'components/ordering/AddToCartButton.tsx',
  'components/ordering/CartLink.tsx',
  'components/ordering/CheckoutForm.tsx',
  'components/ordering/ModifierPickerDialog.tsx',
  'components/ordering/OrderTracker.tsx',
];

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
