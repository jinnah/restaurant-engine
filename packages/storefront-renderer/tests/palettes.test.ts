// @vitest-environment node

// The palette registry is PLATFORM CODE, not tenant input (ADR-024 §5),
// which is exactly why WCAG AA can be a build-time guarantee rather than
// a hope: the set is closed, so every text-on-background pairing the
// shipped stylesheets use is enumerable and provable here.
//
// The pairings below are the complete set the delivered stylesheets
// actually use: `--color-text` and `--color-muted` over `--color-bg` and
// `--color-surface`. `--color-border` is never a text colour (hairlines
// and separators only), and accent-backed text is guarded separately by
// `accentForeground` (accent.test.ts) and `--accent-text`
// (accent-text.test.ts).

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

import { contrastRatio, relativeLuminance } from '../src/accent';
import {
  PALETTE_IDS,
  paletteTokens,
  type PaletteTokens,
} from '../src/theme/palettes';

const AA_BODY = 4.5;
const AA_LARGE = 3;

const base = readFileSync(
  join(__dirname, '..', 'src', 'base.module.css'),
  'utf-8',
);

const contract = JSON.parse(
  readFileSync(
    join(__dirname, '..', '..', 'api-client', 'openapi.json'),
    'utf-8',
  ),
) as { components: { schemas: Record<string, { enum?: string[] }> } };

function ratio(a: string, b: string): number {
  return contrastRatio(relativeLuminance(a), relativeLuminance(b));
}

/** Every text-on-background pairing the shipped stylesheets use. */
function textPairings(
  tokens: PaletteTokens,
): { label: string; fg: string; bg: string }[] {
  return [
    { label: 'text on bg', fg: tokens.text, bg: tokens.bg },
    { label: 'text on surface', fg: tokens.text, bg: tokens.surface },
    { label: 'muted on bg', fg: tokens.muted, bg: tokens.bg },
    { label: 'muted on surface', fg: tokens.muted, bg: tokens.surface },
  ];
}

describe('the palette registry mirrors the contract', () => {
  test('the registered ids are exactly the published enum', () => {
    expect([...PALETTE_IDS]).toEqual(
      contract.components.schemas['PaletteId']?.enum,
    );
  });

  test('every token is a syntactically safe lowercase #rrggbb', () => {
    for (const id of PALETTE_IDS) {
      const tokens = paletteTokens(id);
      for (const value of Object.values(tokens)) {
        expect(value).toMatch(/^#[0-9a-f]{6}$/);
      }
    }
  });

  test('an unregistered stored palette fails closed rather than defaulting', () => {
    expect(() =>
      paletteTokens('sunset' as unknown as (typeof PALETTE_IDS)[number]),
    ).toThrow(/unhandled contract variant/);
  });
});

describe('every palette meets WCAG AA at build time', () => {
  for (const id of PALETTE_IDS) {
    test(`${id}: every text-on-background pairing clears AA`, () => {
      const tokens = paletteTokens(id);
      for (const { label, fg, bg } of textPairings(tokens)) {
        const measured = ratio(fg, bg);
        expect(
          measured,
          `${id} ${label} measured ${measured.toFixed(2)}:1`,
        ).toBeGreaterThanOrEqual(AA_BODY);
        // Body text clears the stricter floor, so large text does too.
        expect(measured).toBeGreaterThanOrEqual(AA_LARGE);
      }
    });
  }
});

describe('warm reproduces the delivered presentation byte for byte', () => {
  // ADR-024 §5: every configuration stored before M4G projects `warm`,
  // so `warm` must be exactly the delivered token set. `base.module.css`
  // still carries those literals as the untokened baseline for the
  // neutral platform surfaces; this pins the two together so neither can
  // drift.
  const warm = paletteTokens('warm');
  const declared: [keyof PaletteTokens, string][] = [
    ['bg', '--color-bg'],
    ['surface', '--color-surface'],
    ['text', '--color-text'],
    ['muted', '--color-muted'],
    ['border', '--color-border'],
  ];

  for (const [key, property] of declared) {
    test(`${property} matches the baseline stylesheet literal`, () => {
      const match = new RegExp(`${property}:\\s*(#[0-9a-f]{6})\\s*;`).exec(
        base,
      );
      expect(match?.[1]).toBe(warm[key]);
    });
  }

  test('the delivered five values are unchanged', () => {
    expect(warm).toEqual({
      bg: '#faf8f5',
      surface: '#ffffff',
      text: '#241f1c',
      muted: '#5f574f',
      border: '#e0dad2',
    });
  });
});
