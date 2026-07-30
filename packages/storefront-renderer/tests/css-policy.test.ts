// @vitest-environment node

// Stylesheet policy pins (ADR-021; extracted here per ADR-022 §2). jsdom
// computes no layout, so the wrapping, typography, and motion floors are
// asserted as policy presence in the committed stylesheets; their visual
// behavior at real widths is browser-level verification (M4F). These
// tests exist so the policies cannot be silently dropped.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

const base = readFileSync(
  join(__dirname, '..', 'src', 'base.module.css'),
  'utf-8',
);
const sections = readFileSync(
  join(__dirname, '..', 'src', 'sections', 'sections.module.css'),
  'utf-8',
);
const classic = readFileSync(
  join(__dirname, '..', 'src', 'variants', 'classic', 'classic.module.css'),
  'utf-8',
);

describe('tenant-page baseline policy', () => {
  test('wrapping floor: unbroken strings wrap instead of overflowing', () => {
    expect(base).toMatch(/overflow-wrap:\s*break-word/);
    expect(base).toMatch(/max-width:\s*100%/);
  });

  test('universal font stack with complex-script fallbacks, no webfont', () => {
    expect(base).toMatch(/font-family:\s*\n?\s*system-ui/);
    expect(base).toContain("'Noto Sans Bengali'");
    expect(base).toContain("'Nirmala UI'");
    expect(base).not.toMatch(/@font-face/);
    expect(base).not.toMatch(/@import/);
    // The universal stack leads; script fallbacks follow it.
    expect(base.indexOf('system-ui')).toBeLessThan(
      base.indexOf("'Noto Sans Bengali'"),
    );
  });

  test('line height accommodates stacked diacritics and conjuncts', () => {
    expect(base).toMatch(/line-height:\s*1\.6/);
  });

  test('reduced-motion floor exists', () => {
    expect(base).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });

  test('focus visibility floor exists', () => {
    expect(base).toMatch(/:focus-visible/);
  });

  test('baseline is scoped: every descendant rule stays zero-specificity', () => {
    // The class block itself carries the root declarations; every
    // descendant selector must go through :where() so the cascade against
    // the component modules is exactly what the original element
    // selectors had (ADR-022 §2).
    const noComments = base.replace(/\/\*[\s\S]*?\*\//g, '');
    const selectors = [...noComments.matchAll(/([^{}]+)\{/g)]
      .map((match) => (match[1] ?? '').trim())
      .filter(
        (selector) =>
          selector !== '' &&
          !selector.startsWith('@') &&
          selector !== '.tenantPage',
      );
    expect(selectors.length).toBeGreaterThan(0);
    for (const selector of selectors) {
      for (const part of selector.split(',')) {
        expect(part.trim()).toMatch(/^:where\(\.tenantPage\)/);
      }
    }
  });
});

describe('interactive target floor (44px minimum)', () => {
  test('the call-to-action and navigation targets declare the floor', () => {
    expect(sections).toMatch(/\.cta[^}]*min-height:\s*44px/s);
    expect(sections).toMatch(/\.cta[^}]*min-width:\s*44px/s);
    expect(classic).toMatch(/\.navLink[^}]*min-height:\s*44px/s);
  });
});
