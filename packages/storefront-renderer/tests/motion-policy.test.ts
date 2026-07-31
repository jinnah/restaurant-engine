// @vitest-environment node

// Motion policy pins (ADR-024 §9). jsdom runs no animation and computes
// no layout, so these assert the AUTHORING rules in the committed
// stylesheets — the rules that make the enhancement safe by
// construction. Real-browser reduced-motion and scroll behaviour are
// M4G-D acceptance.
//
// Five rules are load-bearing and each is asserted here:
//
//   1. every motion declaration sits inside an `@supports` guard;
//   2. every keyframe END state equals the unenhanced base state, so the
//      unsupported path and the reduced-motion path both land on the
//      complete static presentation;
//   3. purchasable content is never animated;
//   4. express ships zero motion;
//   5. the delivered reduced-motion floor is intact and now also
//      detaches scroll timelines.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

const srcRoot = join(__dirname, '..', 'src');

function read(...parts: string[]): string {
  return readFileSync(join(srcRoot, ...parts), 'utf-8');
}

const base = read('base.module.css');
const sections = read('sections', 'sections.module.css');
const menu = read('menu', 'menu.module.css');

const VARIANTS = ['classic', 'editorial', 'express'] as const;
const variantCss: Record<string, string> = Object.fromEntries(
  VARIANTS.map((variant) => [
    variant,
    read('variants', variant, `${variant}.module.css`),
  ]),
);

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

/** The stylesheet with every `@supports { … }` block removed. */
function outsideSupports(css: string): string {
  const source = stripComments(css);
  let out = '';
  let cursor = 0;
  for (;;) {
    const start = source.indexOf('@supports', cursor);
    if (start === -1) {
      out += source.slice(cursor);
      return out;
    }
    out += source.slice(cursor, start);
    let depth = 0;
    let index = source.indexOf('{', start);
    for (; index < source.length; index += 1) {
      if (source[index] === '{') depth += 1;
      else if (source[index] === '}') {
        depth -= 1;
        if (depth === 0) {
          index += 1;
          break;
        }
      }
    }
    cursor = index;
  }
}

/** Every `@keyframes name { … }` block in a stylesheet. */
function keyframeBlocks(css: string): { name: string; body: string }[] {
  const source = stripComments(css);
  const blocks: { name: string; body: string }[] = [];
  const pattern = /@keyframes\s+([\w-]+)\s*\{/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    let depth = 1;
    let index = pattern.lastIndex;
    const start = index;
    for (; index < source.length && depth > 0; index += 1) {
      if (source[index] === '{') depth += 1;
      else if (source[index] === '}') depth -= 1;
    }
    blocks.push({
      name: match[1] ?? '',
      body: source.slice(start, index - 1),
    });
  }
  return blocks;
}

describe('every motion declaration is progressively enhanced', () => {
  for (const variant of VARIANTS) {
    test(`${variant}: no animation or transition outside an @supports guard`, () => {
      const unguarded = outsideSupports(variantCss[variant] ?? '');
      // `@keyframes` may sit at the top level — a definition alone
      // animates nothing. What must be guarded is its APPLICATION.
      const withoutKeyframes = unguarded.replace(/@keyframes[\s\S]*?\n\}/g, '');
      expect(withoutKeyframes).not.toMatch(/\banimation(-[\w-]+)?\s*:/);
      expect(withoutKeyframes).not.toMatch(/\btransition(-[\w-]+)?\s*:/);
    });

    test(`${variant}: the guard is the scroll-timeline feature query`, () => {
      const css = stripComments(variantCss[variant] ?? '');
      for (const guard of css.match(/@supports[^{]*/g) ?? []) {
        expect(guard).toMatch(/animation-timeline:\s*(view|scroll)\(\)/);
      }
    });
  }
});

describe('the unenhanced state is the final state', () => {
  for (const variant of VARIANTS) {
    test(`${variant}: every keyframe ends at the visible base state`, () => {
      for (const block of keyframeBlocks(variantCss[variant] ?? '')) {
        const terminal = /(?:^|\})\s*(?:to|100%)\s*\{([^}]*)\}/.exec(
          block.body,
        );
        expect(
          terminal,
          `${variant}/${block.name} has no terminal step`,
        ).not.toBeNull();
        const declarations = terminal?.[1] ?? '';
        // Anything the animation moves must return to the value the
        // element has with no animation at all.
        if (declarations.includes('opacity')) {
          expect(declarations).toMatch(/opacity:\s*1\b/);
        }
        if (declarations.includes('transform')) {
          expect(declarations).toMatch(/transform:\s*none\b/);
        }
      }
    });
  }
});

describe('purchasable content is never animated', () => {
  test('the shared section and menu stylesheets declare no motion', () => {
    // Motion is variant-scoped by construction; the shared stylesheets
    // that render menu content carry none at all.
    for (const [label, css] of [
      ['sections', sections],
      ['menu', menu],
    ] as const) {
      expect(stripComments(css), label).not.toMatch(
        /\banimation(-[\w-]+)?\s*:/,
      );
      expect(stripComments(css), label).not.toMatch(/@keyframes/);
    }
  });

  for (const variant of VARIANTS) {
    test(`${variant}: no animated selector reaches the menu section`, () => {
      const css = stripComments(variantCss[variant] ?? '');
      for (const block of css.match(/@supports[\s\S]*?\n\}/g) ?? []) {
        for (const selector of block.match(/^\s{2}[^@{}]+\{/gm) ?? []) {
          if (!/\bsection\b/.test(selector)) {
            continue;
          }
          // A selector that reaches sections must either exclude the menu
          // section explicitly, or name a specific section type that is
          // not the menu. Both forms are safe; nothing else is.
          const excludesMenu = selector.includes(
            "not([data-section-type='menu'])",
          );
          const namesOtherType =
            /\[data-section-type='(hero|story|contact|gallery)'\]/.test(
              selector,
            );
          expect(
            excludesMenu || namesOtherType,
            `unguarded section selector: ${selector.trim()}`,
          ).toBe(true);
        }
      }
    });
  }

  test('the /menu listing is structurally out of reach of section motion', () => {
    // Every animated section selector is a DIRECT child of .main. The
    // menu page renders MenuListing (a <div>) into .main, so its
    // category <section> elements are grandchildren and cannot match.
    for (const variant of VARIANTS) {
      const css = stripComments(variantCss[variant] ?? '');
      for (const block of css.match(/@supports[\s\S]*?\n\}/g) ?? []) {
        for (const selector of block.match(/^\s{2}[^@{}]+\{/gm) ?? []) {
          if (/\bsection\b/.test(selector)) {
            expect(selector).toMatch(/\.main\s*>\s*section/);
          }
        }
      }
    }
  });
});

describe('per-variant motion budget', () => {
  test('express ships zero motion', () => {
    const css = stripComments(variantCss['express'] ?? '');
    expect(css).not.toMatch(/@supports/);
    expect(css).not.toMatch(/@keyframes/);
    expect(css).not.toMatch(/\banimation(-[\w-]+)?\s*:/);
  });

  test('classic keeps the minimal treatment: one reveal, hero only', () => {
    const css = stripComments(variantCss['classic'] ?? '');
    expect(keyframeBlocks(css)).toHaveLength(1);
    expect(css).toContain("[data-section-type='hero']");
  });

  test('editorial carries the strongest treatment of the three', () => {
    const editorial = keyframeBlocks(variantCss['editorial'] ?? '').length;
    const classic = keyframeBlocks(variantCss['classic'] ?? '').length;
    const express = keyframeBlocks(variantCss['express'] ?? '').length;
    expect(editorial).toBeGreaterThan(classic);
    expect(classic).toBeGreaterThan(express);
  });

  test('no animation library, no client hook, no forced timeline', () => {
    for (const variant of VARIANTS) {
      const css = stripComments(variantCss[variant] ?? '');
      // Only the native scroll-progress timelines are permitted; a named
      // or overridden timeline would imply script-driven control.
      for (const declaration of css.match(/animation-timeline:[^;]+;/g) ?? []) {
        expect(declaration).toMatch(/animation-timeline:\s*(view|scroll)\(\)/);
      }
      expect(css).not.toMatch(/scroll-behavior:\s*smooth/);
    }
  });
});

describe('the reduced-motion floor', () => {
  test('every delivered safeguard survives, plus timeline detachment', () => {
    const block = /@media \(prefers-reduced-motion: reduce\)([\s\S]*)$/.exec(
      base,
    )?.[1];
    expect(block).toBeDefined();
    for (const declaration of [
      /animation-duration:\s*0\.01ms !important/,
      /animation-iteration-count:\s*1 !important/,
      /animation-timeline:\s*auto !important/,
      /scroll-behavior:\s*auto !important/,
      /transition-duration:\s*0\.01ms !important/,
    ]) {
      expect(block).toMatch(declaration);
    }
  });

  test('the floor applies to every descendant of the tenant page', () => {
    expect(base).toMatch(
      /@media \(prefers-reduced-motion: reduce\)\s*\{\s*:where\(\.tenantPage\) \*/,
    );
  });
});
