// The one place a stored theme becomes CSS custom properties (M4G-B,
// ADR-024 §5).
//
// `themeStyle` is pure and framework-neutral: registered ids in, a plain
// style object out. It is applied to **the element that carries
// `tenantPageClass`** — the public storefront's `<body>` and the control
// centre's preview container — rather than to each variant's root, so the
// tokens reach the painted browser canvas as well as every descendant.
// Setting them on a descendant would leave `<body>`'s background (which
// the browser propagates to the canvas) on the baseline palette, showing
// the wrong colour behind a dark page. One typed source, one application
// site, identical in public and preview.
//
// Nothing here is persisted and nothing is rewritten: the stored accent
// travels through `safeAccent` exactly as delivered, and palette and
// pairing are re-read on every render, so changing a palette re-derives
// the tokens rather than mutating a configuration (ADR-024 §5).
//
// Variant chrome does **not** live here. Spacing, radius, and per-variant
// type scale are tokens a variant root sets for itself (ADR-024 §8);
// `themeStyle` carries only tenant-selected theme content.

import type { CSSProperties } from 'react';

import { accentForeground, safeAccent } from '../accent';
import type { PublicTheme } from '../contract';
import { paletteTokens } from './palettes';
import { typePairingTokens } from './type-pairings';

/**
 * The complete tenant-page custom-property set for one published theme.
 *
 * Neutral platform surfaces (the 404 and the generic error document) get
 * no theme at all — they are not a tenant's page — and fall back to the
 * baseline declarations in `base.module.css`.
 */
export function themeStyle(theme: PublicTheme): CSSProperties {
  const accent = safeAccent(theme.accent);
  const palette = paletteTokens(theme.palette);
  const pairing = typePairingTokens(theme.type_pairing);
  return {
    '--color-bg': palette.bg,
    '--color-surface': palette.surface,
    '--color-text': palette.text,
    '--color-muted': palette.muted,
    '--color-border': palette.border,
    '--accent': accent,
    '--accent-contrast': accentForeground(accent),
    '--font-body': pairing.body,
    '--font-heading': pairing.heading,
    '--type-scale': pairing.scale,
    '--heading-weight': pairing.headingWeight,
    '--heading-tracking': pairing.headingTracking,
  } as CSSProperties;
}
