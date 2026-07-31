import type { CSSProperties } from 'react';
import type { PaletteId, TypePairingId } from '@restaurant-engine/api-client';
import {
  PALETTE_IDS,
  TYPE_PAIRING_IDS,
  paletteTokens,
  typePairingTokens,
} from '@restaurant-engine/storefront-renderer';

/**
 * Owner-facing naming for the two curated theme registries (M4G-C,
 * ADR-024 §3).
 *
 * Two properties are load-bearing here.
 *
 * **Exhaustiveness.** Both records are keyed by the generated contract
 * union, so a sixth palette or fourth pairing added to the backend
 * registry fails this file's typecheck until it is named and described.
 * That is the same `Record<…>` discipline `SECTION_TYPE_LABELS` uses, and
 * it is why no fallback label exists: an unnamed registry entry must be a
 * build failure, never a blank option.
 *
 * **No transcription.** Every colour and font stack shown beside a choice
 * is read from the renderer's own registries through {@link
 * paletteSwatchStyle} and {@link typeSampleStyle}. The control center
 * holds no palette hex and no font stack of its own, so a swatch cannot
 * drift from what the storefront actually renders (ADR-004: no
 * handwritten copies of a shared contract).
 */
export interface BrandChoice {
  /** The product name, e.g. "Midnight". */
  readonly label: string;
  /** What the choice actually looks like, in plain words. */
  readonly description: string;
}

/** The five curated palettes, described so colour is never the only cue. */
export const PALETTE_CHOICES: Record<PaletteId, BrandChoice> = {
  warm: {
    label: 'Warm',
    description: 'warm neutrals on an off-white page',
  },
  ember: {
    label: 'Ember',
    description: 'deeper warm neutrals with stronger contrast',
  },
  slate: { label: 'Slate', description: 'cool gray neutrals' },
  olive: { label: 'Olive', description: 'muted green-leaning neutrals' },
  midnight: {
    label: 'Midnight',
    description: 'a dark page with light text',
  },
};

/** The three curated typography pairings (system stacks only, §6). */
export const TYPE_PAIRING_CHOICES: Record<TypePairingId, BrandChoice> = {
  humanist: {
    label: 'Humanist',
    description: 'one clear sans-serif for headings and text',
  },
  serif_display: {
    label: 'Serif display',
    description: 'serif headings above sans-serif text',
  },
  geometric: {
    label: 'Geometric',
    description: 'tighter geometric headings at a larger scale',
  },
};

/**
 * Offer order, taken from the renderer's registries rather than restated,
 * so the control center cannot present a different order — or a different
 * set — from the one that renders.
 */
export const PALETTE_ORDER: readonly PaletteId[] = PALETTE_IDS;
export const TYPE_PAIRING_ORDER: readonly TypePairingId[] = TYPE_PAIRING_IDS;

/** One option's text: the name, then what it looks like. Never colour alone. */
export function brandChoiceText(choice: BrandChoice): string {
  return `${choice.label} — ${choice.description}`;
}

/**
 * The decorative swatch for one palette, painted with that palette's own
 * page, text, and border tokens. Purely visual: the option text carries
 * the meaning, so every swatch is `aria-hidden`.
 */
export function paletteSwatchStyle(palette: PaletteId): CSSProperties {
  const tokens = paletteTokens(palette);
  return {
    background: tokens.bg,
    borderColor: tokens.border,
    color: tokens.text,
  };
}

/** The decorative type sample for one pairing, in that pairing's heading stack. */
export function typeSampleStyle(pairing: TypePairingId): CSSProperties {
  return { fontFamily: typePairingTokens(pairing).heading };
}
