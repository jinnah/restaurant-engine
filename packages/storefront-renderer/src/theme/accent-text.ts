// The palette-aware accent TEXT token (M4G-B, ADR-024 §5).
//
// `accentForeground` (accent.ts) solves one direction — text drawn *on*
// an accent background, the call to action. The delivered stylesheets
// also use the raw accent as text and as the focus-ring colour (the link
// colour, the classic nav link, the featured badge), and nothing guards
// that direction: a pathological light accent already reads poorly on
// `#faf8f5`, and against the `midnight` palette a dark accent would be
// unreadable. `--accent-text` is that missing guard.
//
// The derivation walks LIGHTNESS while preserving the accent's hue and
// saturation, so the tenant's colour identity survives — this is not a
// hue change. It is computed at render time from the stored accent and
// that version's palette and is **never persisted**: the configuration
// keeps exactly the accent the owner chose, and changing palette
// re-derives the token on the next render.
//
// `--accent` remains the decorative-fill token (backgrounds, borders);
// text, focus indicators, and other contrast-required uses read
// `--accent-text`.
//
// Determinism is a requirement, not a nicety: the same accent and
// palette must always produce the same token, because the value ships in
// server-rendered HTML.

import { contrastRatio, relativeLuminance, safeAccent } from '../accent';
import type { PaletteTokens } from './palettes';

/** The WCAG AA body-text floor. Production never uses another value. */
export const AA_BODY = 4.5;

/** One 8-bit step per channel-space walk; 256 candidates per direction. */
const STEP = 1 / 256;

interface Hsl {
  readonly h: number;
  readonly s: number;
  readonly l: number;
}

function toRgb(hex: string): [number, number, number] {
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ];
}

function toHex(r: number, g: number, b: number): string {
  const part = (value: number) =>
    Math.max(0, Math.min(255, value)).toString(16).padStart(2, '0');
  return `#${part(r)}${part(g)}${part(b)}`;
}

function rgbToHsl(r: number, g: number, b: number): Hsl {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) {
    return { h: 0, s: 0, l };
  }
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === rn) {
    h = ((((gn - bn) / d) % 6) + 6) % 6;
  } else if (max === gn) {
    h = (bn - rn) / d + 2;
  } else {
    h = (rn - gn) / d + 4;
  }
  return { h: h * 60, s, l };
}

/** HSL to the exact integer RGB that will be emitted (rounded here). */
function hslToHex(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let rp = 0;
  let gp = 0;
  let bp = 0;
  if (hp < 1) [rp, gp, bp] = [c, x, 0];
  else if (hp < 2) [rp, gp, bp] = [x, c, 0];
  else if (hp < 3) [rp, gp, bp] = [0, c, x];
  else if (hp < 4) [rp, gp, bp] = [0, x, c];
  else if (hp < 5) [rp, gp, bp] = [x, 0, c];
  else [rp, gp, bp] = [c, 0, x];
  const m = l - c / 2;
  return toHex(
    Math.round((rp + m) * 255),
    Math.round((gp + m) * 255),
    Math.round((bp + m) * 255),
  );
}

/**
 * Derive the accent text token.
 *
 * `floor` exists so the fallback branch is reachable in tests: with the
 * shipped palettes no accent ever needs it (one endpoint of the preferred
 * direction always conforms), which is proved rather than assumed. It is
 * deliberately NOT part of the package's public surface — production
 * always uses the AA body floor.
 */
export function deriveAccentText(
  accent: string,
  palette: PaletteTokens,
  floor: number = AA_BODY,
): string {
  const safe = safeAccent(accent);
  const backgrounds = [
    relativeLuminance(palette.bg),
    relativeLuminance(palette.surface),
  ];
  const conforms = (candidate: string): boolean => {
    const luminance = relativeLuminance(candidate);
    return backgrounds.every(
      (background) => contrastRatio(luminance, background) >= floor,
    );
  };

  // 1. The stored accent is kept untouched whenever it already conforms
  //    against both surfaces the stylesheets draw accent text on.
  if (conforms(safe)) {
    return safe;
  }

  const [r, g, b] = toRgb(safe);
  const { h, s, l } = rgbToHsl(r, g, b);

  // 2. Deterministic direction order: away from the background lightness
  //    first — darken on a light palette, lighten on a dark one.
  const darkenFirst =
    relativeLuminance(palette.text) < relativeLuminance(palette.bg);
  const directions: readonly (-1 | 1)[] = darkenFirst ? [-1, 1] : [1, -1];

  for (const direction of directions) {
    // 3. Stepped candidates: hue and saturation preserved, lightness
    //    walked in fixed 1/256 increments, each converted to the exact
    //    integer RGB that will be emitted and tested in that form.
    for (let step = 1; ; step += 1) {
      const candidateL = l + direction * step * STEP;
      if (candidateL <= 0 || candidateL >= 1) {
        break;
      }
      const candidate = hslToHex(h, s, candidateL);
      if (conforms(candidate)) {
        return candidate;
      }
    }
    // 4. The exact endpoint, always tested explicitly. A lightness
    //    derived from 8-bit RGB is not aligned to the 1/256 grid, so the
    //    stepped loop above is not guaranteed to land on 0 or 1 — the
    //    endpoint must be evaluated in its own right, not assumed
    //    reached.
    const endpoint = direction < 0 ? '#000000' : '#ffffff';
    if (conforms(endpoint)) {
      return endpoint;
    }
  }

  // 5. Neither direction conforms, both exact endpoints included: fall
  //    back to the palette's own text colour, which the per-palette
  //    contrast suite proves conformant against bg and surface.
  return palette.text;
}

/** The `--accent-text` value for a stored accent under a palette. */
export function accentText(accent: string, palette: PaletteTokens): string {
  return deriveAccentText(accent, palette, AA_BODY);
}
