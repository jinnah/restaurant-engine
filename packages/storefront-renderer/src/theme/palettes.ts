// The renderer-side palette registry (M4G-B, ADR-024 §3/§5).
//
// The backend owns `PaletteId` as an append-only closed enum; this module
// is its renderer mirror: one exhaustive typed map from registered id to
// the five `.tenantPage` colour tokens every variant and section
// stylesheet already consumes. `satisfies Record<PaletteId, …>` makes the
// map compile-time complete — a registry entry cannot ship without its
// rendering tokens — and the lookup ends in `assertNever`, so runtime
// drift (a stale deployment against a newer API) throws into the generic
// error boundary rather than rendering a guessed palette (ADR-024 §10).
//
// A palette is **platform code, not tenant input**, which is exactly why
// contrast can be a build-time guarantee: `tests/palettes.test.ts` proves
// every text-on-background pairing the shipped stylesheets use clears
// WCAG AA against every registered palette. The tenant accent remains the
// single arbitrary token and never participates in these five colours.
//
// `warm` reproduces the delivered presentation **byte for byte** (ADR-024
// §5), so every configuration stored before M4G renders exactly as it
// does today; `tests/palettes.test.ts` pins those five values against the
// literals `base.module.css` still carries as its untokened baseline.

import { assertNever } from '../assert-never';
import type { PaletteId } from '../contract';

export interface PaletteTokens {
  /** `--color-bg`: the page background, and the painted browser canvas. */
  readonly bg: string;
  /** `--color-surface`: chrome, cards, and badges raised off the page. */
  readonly surface: string;
  /** `--color-text`: body copy and headings. */
  readonly text: string;
  /** `--color-muted`: secondary copy — still AA against bg and surface. */
  readonly muted: string;
  /** `--color-border`: hairlines and separators; never a text colour. */
  readonly border: string;
}

const PALETTES = {
  // The delivered scheme, reproduced exactly (ADR-024 §5).
  warm: {
    bg: '#faf8f5',
    surface: '#ffffff',
    text: '#241f1c',
    muted: '#5f574f',
    border: '#e0dad2',
  },
  // Deeper warm neutrals with a heavier surface contrast.
  ember: {
    bg: '#f4ece4',
    surface: '#fffaf5',
    text: '#2a1c14',
    muted: '#5d4636',
    border: '#ddc9b6',
  },
  // Cool grey neutrals.
  slate: {
    bg: '#f4f6f8',
    surface: '#ffffff',
    text: '#1b2027',
    muted: '#525c68',
    border: '#d5dbe2',
  },
  // Muted green-leaning neutrals.
  olive: {
    bg: '#f4f5ee',
    surface: '#fdfdf8',
    text: '#1f2418',
    muted: '#535b45',
    border: '#d7dbc7',
  },
  // The dark scheme: dark background, light text.
  midnight: {
    bg: '#14171c',
    surface: '#1e232a',
    text: '#f2f4f7',
    muted: '#adb6c2',
    border: '#333b45',
  },
} as const satisfies Record<PaletteId, PaletteTokens>;

/** Every registered palette id, for the build-time contrast suites. */
export const PALETTE_IDS = Object.keys(PALETTES) as readonly PaletteId[];

/** The tokens for a registered palette; fails closed on runtime drift. */
export function paletteTokens(palette: PaletteId): PaletteTokens {
  switch (palette) {
    case 'warm':
      return PALETTES.warm;
    case 'ember':
      return PALETTES.ember;
    case 'slate':
      return PALETTES.slate;
    case 'olive':
      return PALETTES.olive;
    case 'midnight':
      return PALETTES.midnight;
    default:
      return assertNever(palette);
  }
}
