// @vitest-environment node

// Typography pairings are curated SYSTEM stacks only (ADR-024 §6): no
// webfont ships, so there is no request, no CLS, no licensing or
// subsetting surface, and no supply-chain change. Two properties matter
// and are asserted here rather than trusted: every stack keeps the
// complex-script system fallbacks the delivered stack carries (ADR-021
// §9), and `humanist` reproduces the delivered typography exactly.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

import {
  DELIVERED_BODY_STACK,
  TYPE_PAIRING_IDS,
  typePairingTokens,
} from '../src/theme/type-pairings';

const srcRoot = join(__dirname, '..', 'src');

const base = readFileSync(join(srcRoot, 'base.module.css'), 'utf-8');

const contract = JSON.parse(
  readFileSync(
    join(__dirname, '..', '..', 'api-client', 'openapi.json'),
    'utf-8',
  ),
) as { components: { schemas: Record<string, { enum?: string[] }> } };

function stylesheets(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      found.push(...stylesheets(path));
    } else if (entry.endsWith('.css')) {
      found.push(path);
    }
  }
  return found;
}

describe('the pairing registry mirrors the contract', () => {
  test('the registered ids are exactly the published enum', () => {
    expect([...TYPE_PAIRING_IDS]).toEqual(
      contract.components.schemas['TypePairingId']?.enum,
    );
  });

  test('an unregistered stored pairing fails closed rather than defaulting', () => {
    expect(() =>
      typePairingTokens(
        'brutalist' as unknown as (typeof TYPE_PAIRING_IDS)[number],
      ),
    ).toThrow(/unhandled contract variant/);
  });
});

describe('no webfont ships, in any stylesheet', () => {
  test('no @font-face and no @import anywhere in the package', () => {
    const sheets = stylesheets(srcRoot);
    expect(sheets.length).toBeGreaterThan(0);
    for (const sheet of sheets) {
      const source = readFileSync(sheet, 'utf-8');
      expect(source, sheet).not.toMatch(/@font-face/);
      expect(source, sheet).not.toMatch(/@import/);
    }
  });
});

describe('every stack preserves the complex-script fallbacks', () => {
  for (const id of TYPE_PAIRING_IDS) {
    test(`${id}: heading and body stacks keep the script fallbacks`, () => {
      const tokens = typePairingTokens(id);
      for (const stack of [tokens.heading, tokens.body]) {
        // A Bengali-capable system face and the Windows complex-script
        // face, after the primary faces, before the generic family.
        expect(stack).toMatch(/'Noto (Sans|Serif) Bengali'/);
        expect(stack).toContain("'Nirmala UI'");
        expect(stack).toMatch(/(sans-serif|serif)$/);
        // The script fallbacks follow the primary faces, never lead.
        expect(stack.indexOf("'Noto")).toBeGreaterThan(0);
      }
    });
  }
});

describe('humanist reproduces the delivered typography', () => {
  const humanist = typePairingTokens('humanist');

  test('the body and heading stacks are the delivered universal stack', () => {
    expect(humanist.body).toBe(DELIVERED_BODY_STACK);
    expect(humanist.heading).toBe(DELIVERED_BODY_STACK);
  });

  test('the delivered stack matches the baseline stylesheet fallback', () => {
    // `base.module.css` keeps the delivered stack as the `--font-body`
    // fallback for the unthemed platform surfaces; the two must agree
    // family for family, in order.
    const fallback = /--font-body,([\s\S]*?)\n  \);/.exec(base)?.[1] ?? '';
    const families = fallback
      .split(',')
      .map((part) => part.trim())
      .filter((part) => part !== '');
    expect(families.join(', ')).toBe(DELIVERED_BODY_STACK);
  });

  test('the delivered scale and heading defaults are unchanged', () => {
    expect(humanist.scale).toBe('1');
    expect(humanist.headingWeight).toBe('bold');
    expect(humanist.headingTracking).toBe('normal');
  });
});
