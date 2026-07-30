// @vitest-environment node

// Stylesheet policy pins (ADR-021). jsdom computes no layout, so the
// wrapping, typography, and motion floors are asserted as policy presence
// in the committed stylesheets; their visual behavior at real widths is
// browser-level verification (M4F). These tests exist so the policies
// cannot be silently dropped.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

const globals = readFileSync(
  join(__dirname, '..', 'app', 'globals.css'),
  'utf-8',
);
const sections = readFileSync(
  join(__dirname, '..', 'components', 'sections', 'sections.module.css'),
  'utf-8',
);
const classic = readFileSync(
  join(
    __dirname,
    '..',
    'components',
    'variants',
    'classic',
    'classic.module.css',
  ),
  'utf-8',
);

describe('global stylesheet policy', () => {
  test('wrapping floor: unbroken strings wrap instead of overflowing', () => {
    expect(globals).toMatch(/overflow-wrap:\s*break-word/);
    expect(globals).toMatch(/max-width:\s*100%/);
  });

  test('universal font stack with complex-script fallbacks, no webfont', () => {
    expect(globals).toMatch(/font-family:\s*\n?\s*system-ui/);
    expect(globals).toContain("'Noto Sans Bengali'");
    expect(globals).toContain("'Nirmala UI'");
    expect(globals).not.toMatch(/@font-face/);
    expect(globals).not.toMatch(/@import/);
    // The universal stack leads; script fallbacks follow it.
    expect(globals.indexOf('system-ui')).toBeLessThan(
      globals.indexOf("'Noto Sans Bengali'"),
    );
  });

  test('line height accommodates stacked diacritics and conjuncts', () => {
    expect(globals).toMatch(/line-height:\s*1\.6/);
  });

  test('reduced-motion floor exists', () => {
    expect(globals).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });

  test('focus visibility floor exists', () => {
    expect(globals).toMatch(/:focus-visible/);
  });
});

describe('interactive target floor (44px minimum)', () => {
  test('the call-to-action and navigation targets declare the floor', () => {
    expect(sections).toMatch(/\.cta[^}]*min-height:\s*44px/s);
    expect(sections).toMatch(/\.cta[^}]*min-width:\s*44px/s);
    expect(classic).toMatch(/\.navLink[^}]*min-height:\s*44px/s);
  });
});
