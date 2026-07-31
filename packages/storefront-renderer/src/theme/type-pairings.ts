// The renderer-side typography registry (M4G-B, ADR-024 §3/§6).
//
// The mirror of the backend's append-only `TypePairingId`, in the same
// shape as the palette registry: an exhaustive typed map pinned by tests,
// with an `assertNever` lookup so an unregistered stored value fails
// closed instead of rendering a guessed pairing.
//
// **No webfont ships** (ADR-024 §6). Each pairing is a curated pair of
// *system* font stacks plus a bounded scale delivered as custom
// properties: zero network cost, zero CLS, no licensing or subsetting
// surface, and no supply-chain change. Every stack — heading and body
// alike — keeps the complex-script system fallbacks the delivered stack
// carries (`Noto Sans Bengali` / `Noto Serif Bengali`, `Nirmala UI`)
// after its primary faces, preserving the ADR-021 §9 Unicode posture;
// `tests/type-pairings.test.ts` asserts that for every stack.
//
// `humanist` reproduces the delivered stack and heading scale exactly
// (ADR-024 §5): its `scale` is 1 and its stacks are the literals
// `base.module.css` still carries as its untokened baseline, so every
// pre-M4G configuration renders with identical computed typography.

import { assertNever } from '../assert-never';
import type { TypePairingId } from '../contract';

export interface TypePairingTokens {
  /** `--font-heading`: the stack for h1/h2/h3. */
  readonly heading: string;
  /** `--font-body`: the stack the tenant page inherits. */
  readonly body: string;
  /** `--type-scale`: unitless multiplier over the delivered heading sizes. */
  readonly scale: string;
  /** `--heading-weight`: `bold` reproduces the delivered UA default. */
  readonly headingWeight: string;
  /** `--heading-tracking`: `normal` reproduces the delivered default. */
  readonly headingTracking: string;
}

// The delivered universal stack (ADR-021 §9), verbatim. Kept as one
// constant so a pairing that means "the delivered body text" cannot drift
// from it by transcription.
const UNIVERSAL_SANS =
  "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'Noto Sans Bengali', 'Nirmala UI', sans-serif";

const SYSTEM_SERIF =
  "ui-serif, Georgia, Cambria, 'Times New Roman', Times, 'Noto Serif', 'Noto Serif Bengali', 'Nirmala UI', serif";

const GEOMETRIC_SANS =
  "'Avenir Next', Avenir, 'Segoe UI Variable Display', 'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'Noto Sans Bengali', 'Nirmala UI', sans-serif";

const TYPE_PAIRINGS = {
  // The delivered typography, reproduced exactly (ADR-024 §5).
  humanist: {
    heading: UNIVERSAL_SANS,
    body: UNIVERSAL_SANS,
    scale: '1',
    headingWeight: 'bold',
    headingTracking: 'normal',
  },
  // System serif headings over the humanist body stack.
  serif_display: {
    heading: SYSTEM_SERIF,
    body: UNIVERSAL_SANS,
    scale: '1.05',
    headingWeight: 'bold',
    headingTracking: '-0.01em',
  },
  // Tighter geometric-leaning system sans headings, wider heading scale.
  geometric: {
    heading: GEOMETRIC_SANS,
    body: UNIVERSAL_SANS,
    scale: '1.15',
    headingWeight: '600',
    headingTracking: '-0.02em',
  },
} as const satisfies Record<TypePairingId, TypePairingTokens>;

/** Every registered pairing id, for the build-time typography suites. */
export const TYPE_PAIRING_IDS = Object.keys(
  TYPE_PAIRINGS,
) as readonly TypePairingId[];

/** The delivered stack, exported so the compatibility pin has one source. */
export const DELIVERED_BODY_STACK: string = UNIVERSAL_SANS;

/** The tokens for a registered pairing; fails closed on runtime drift. */
export function typePairingTokens(pairing: TypePairingId): TypePairingTokens {
  switch (pairing) {
    case 'humanist':
      return TYPE_PAIRINGS.humanist;
    case 'serif_display':
      return TYPE_PAIRINGS.serif_display;
    case 'geometric':
      return TYPE_PAIRINGS.geometric;
    default:
      return assertNever(pairing);
  }
}
