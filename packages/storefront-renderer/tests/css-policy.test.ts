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
function variantStylesheet(variant: string): string {
  return readFileSync(
    join(__dirname, '..', 'src', 'variants', variant, `${variant}.module.css`),
    'utf-8',
  );
}

const VARIANT_STYLESHEETS = ['classic', 'editorial', 'express'].map(
  (variant) => [variant, variantStylesheet(variant)] as const,
);

/**
 * Split a selector list on its TOP-LEVEL commas only.
 *
 * A naive `split(',')` tears functional pseudo-classes apart —
 * `:where(.tenantPage) :is(h1, h2, h3)` becomes three fragments, two of
 * which look unscoped — which would report a false violation for a
 * selector that is in fact correctly scoped. Depth tracking keeps the
 * policy exactly as strict while judging whole compound selectors.
 */
function selectorList(selector: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let current = '';
  for (const character of selector) {
    if (character === '(') depth += 1;
    if (character === ')') depth -= 1;
    if (character === ',' && depth === 0) {
      parts.push(current.trim());
      current = '';
      continue;
    }
    current += character;
  }
  parts.push(current.trim());
  return parts.filter((part) => part !== '');
}

describe('tenant-page baseline policy', () => {
  test('wrapping floor: unbroken strings wrap instead of overflowing', () => {
    expect(base).toMatch(/overflow-wrap:\s*break-word/);
    expect(base).toMatch(/max-width:\s*100%/);
  });

  test('universal font stack with complex-script fallbacks, no webfont', () => {
    // M4G-B: the stack is now the `--font-body` fallback (the pairing
    // registry supplies the token). The delivered families, their order,
    // and the no-webfont rule are unchanged; type-pairings.test.ts pins
    // this fallback equal to the `humanist` stack.
    expect(base).toMatch(/font-family:\s*var\(\s*\n?\s*--font-body,/);
    expect(base).toMatch(/--font-body,\s*\n?\s*system-ui/);
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

  test('heading typography reads the pairing tokens at zero specificity', () => {
    expect(base).toMatch(
      /:where\(\.tenantPage\) :is\(h1, h2, h3\)[^}]*font-family:\s*var\(--font-heading/s,
    );
    // The delivered heading size survives as the scale's base term.
    expect(base).toMatch(
      /font-size:\s*calc\(1\.75rem \* var\(--type-scale, 1\)\)/,
    );
  });

  test('reduced-motion floor exists and neutralises scroll timelines', () => {
    expect(base).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    // Every delivered safeguard is preserved, plus the M4G-B addition
    // (ADR-024 §9): a scroll-driven animation is progress-based, so it is
    // detached from its timeline as well as duration-collapsed.
    for (const declaration of [
      /animation-duration:\s*0\.01ms !important/,
      /animation-iteration-count:\s*1 !important/,
      /animation-timeline:\s*auto !important/,
      /scroll-behavior:\s*auto !important/,
      /transition-duration:\s*0\.01ms !important/,
    ]) {
      expect(base).toMatch(declaration);
    }
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
      for (const part of selectorList(selector)) {
        expect(part).toMatch(/^:where\(\.tenantPage\)/);
      }
    }
  });
});

describe('interactive target floor (44px minimum)', () => {
  test('the shared call to action declares the floor', () => {
    expect(sections).toMatch(/\.cta[^}]*min-height:\s*44px/s);
    expect(sections).toMatch(/\.cta[^}]*min-width:\s*44px/s);
  });

  // The floor is variant-independent: a variant may restyle its
  // navigation freely but may not shrink the target below the platform
  // minimum (ADR-021 §10).
  for (const [variant, stylesheet] of VARIANT_STYLESHEETS) {
    test(`${variant}: the navigation target declares the floor`, () => {
      expect(stylesheet).toMatch(/\.navLink[^}]*min-height:\s*44px/s);
      expect(stylesheet).toMatch(/\.navLink[^}]*min-width:\s*44px/s);
    });
  }
});
