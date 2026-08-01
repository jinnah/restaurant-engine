// @vitest-environment node

// The `--accent-text` guarantee (ADR-024 §5), proved rather than trusted.
//
// Coverage strategy, stated plainly because sampling alone would not be
// honest here:
//
//   * The derivation SEARCHES until the emitted colour conforms, so any
//     value it returns from the walk satisfies the floor **by
//     construction**. The real risks are non-termination and a
//     wrong-direction choice.
//   * Termination is therefore proved ANALYTICALLY, not sampled: for
//     each palette, the exact endpoint of the preferred direction
//     (black on a light palette, white on a dark one) is asserted
//     conformant. Because that endpoint is always evaluated explicitly,
//     the search resolves for every one of the 16,777,216 sRGB inputs.
//   * The cube sweeps below are corroboration on top of that proof: a
//     4,096-point sample against every palette, and a much denser
//     140,608-point sweep against `midnight`, the hardest palette.

import { describe, expect, test } from 'vitest';

import { contrastRatio, relativeLuminance } from '../src/accent';
import {
  AA_BODY,
  accentText,
  deriveAccentText,
} from '../src/theme/accent-text';
import {
  PALETTE_IDS,
  paletteTokens,
  type PaletteTokens,
} from '../src/theme/palettes';

function hex(r: number, g: number, b: number): string {
  const part = (v: number) => v.toString(16).padStart(2, '0');
  return `#${part(r)}${part(g)}${part(b)}`;
}

/** The worst contrast of a colour against both surfaces of a palette. */
function worstRatio(colour: string, palette: PaletteTokens): number {
  const luminance = relativeLuminance(colour);
  return Math.min(
    contrastRatio(luminance, relativeLuminance(palette.bg)),
    contrastRatio(luminance, relativeLuminance(palette.surface)),
  );
}

function hue(colour: string): number {
  const [r, g, b] = [
    Number.parseInt(colour.slice(1, 3), 16) / 255,
    Number.parseInt(colour.slice(3, 5), 16) / 255,
    Number.parseInt(colour.slice(5, 7), 16) / 255,
  ];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max === min) return 0;
  const d = max - min;
  const raw =
    max === r
      ? ((g - b) / d) % 6
      : max === g
        ? (b - r) / d + 2
        : (r - g) / d + 4;
  return (((raw * 60) % 360) + 360) % 360;
}

describe('termination is proved, not sampled', () => {
  for (const id of PALETTE_IDS) {
    test(`${id}: the preferred direction's exact endpoint conforms`, () => {
      const palette = paletteTokens(id);
      const lightPalette =
        relativeLuminance(palette.text) < relativeLuminance(palette.bg);
      const endpoint = lightPalette ? '#000000' : '#ffffff';
      // Every candidate walk ends by evaluating this exact endpoint, so a
      // conformant endpoint means the search resolves for EVERY sRGB
      // input against this palette - no lightness-grid assumption needed.
      expect(worstRatio(endpoint, palette)).toBeGreaterThanOrEqual(AA_BODY);
    });
  }
});

describe('the emitted token conforms across the sRGB input space', () => {
  for (const id of PALETTE_IDS) {
    test(`${id}: 4,096-point cube sample clears AA against bg and surface`, () => {
      const palette = paletteTokens(id);
      let worst = Number.POSITIVE_INFINITY;
      for (let r = 0; r <= 255; r += 17) {
        for (let g = 0; g <= 255; g += 17) {
          for (let b = 0; b <= 255; b += 17) {
            const emitted = accentText(hex(r, g, b), palette);
            const ratio = worstRatio(emitted, palette);
            worst = Math.min(worst, ratio);
            expect(ratio).toBeGreaterThanOrEqual(AA_BODY);
          }
        }
      }
      // The floor is reached exactly, because the walk stops at the first
      // conforming step - evidence the search is not overshooting.
      expect(worst).toBeGreaterThanOrEqual(AA_BODY);
      expect(worst).toBeLessThan(AA_BODY + 0.5);
    });
  }

  // The one test in this repository that carries its own timeout, and it
  // is a duration allowance rather than a change of subject: 52^3 =
  // 140,608 exhaustive derivations, each a search, run close enough to
  // Vitest's 5,000 ms default that ordinary CI-runner variance decides the
  // outcome. It passed the pull-request run at 5,366 ms for this file and
  // crossed the limit at 6,253 ms on the merge commit, with a byte-
  // identical tree and no assertion failure. Sampling fewer points, or
  // splitting the sweep to fit, would quietly weaken the property this
  // suite exists to prove, so the budget moves instead. The limit stays
  // per-test rather than global, so every other test in this package keeps
  // the 5,000 ms default and a genuine hang here still fails.
  test('midnight: 140,608-point dense sweep (the hardest palette)', () => {
    const palette = paletteTokens('midnight');
    for (let r = 0; r <= 255; r += 5) {
      for (let g = 0; g <= 255; g += 5) {
        for (let b = 0; b <= 255; b += 5) {
          expect(
            worstRatio(accentText(hex(r, g, b), palette), palette),
          ).toBeGreaterThanOrEqual(AA_BODY);
        }
      }
    }
  }, 15_000);

  test('a full hue sweep at maximum saturation conforms for every palette', () => {
    for (const id of PALETTE_IDS) {
      const palette = paletteTokens(id);
      for (let h = 0; h < 360; h += 1) {
        // Fully saturated mid-lightness colours: the hardest inputs, and
        // the ones a lightness walk has least room to move.
        const rad = (h / 60) % 6;
        const c = 1;
        const x = c * (1 - Math.abs((rad % 2) - 1));
        const [rp, gp, bp] =
          rad < 1
            ? [c, x, 0]
            : rad < 2
              ? [x, c, 0]
              : rad < 3
                ? [0, c, x]
                : rad < 4
                  ? [0, x, c]
                  : rad < 5
                    ? [x, 0, c]
                    : [c, 0, x];
        const accent = hex(
          Math.round(rp * 255),
          Math.round(gp * 255),
          Math.round(bp * 255),
        );
        expect(
          worstRatio(accentText(accent, palette), palette),
        ).toBeGreaterThanOrEqual(AA_BODY);
      }
    }
  });
});

describe('the stored accent is preserved whenever it already conforms', () => {
  test('the platform default renders identically on every light palette', () => {
    // ADR-024 §5's bounded appearance guarantee: an accent that already
    // clears the floor is returned UNCHANGED, so nothing about an
    // untouched configuration's appearance moves.
    for (const id of ['warm', 'ember', 'slate', 'olive'] as const) {
      expect(accentText('#a34b2a', paletteTokens(id))).toBe('#a34b2a');
    }
  });

  test('a failing accent changes only by becoming legible', () => {
    const midnight = paletteTokens('midnight');
    const derived = accentText('#a34b2a', midnight);
    expect(derived).not.toBe('#a34b2a');
    expect(worstRatio(derived, midnight)).toBeGreaterThanOrEqual(AA_BODY);
  });

  test('black and white accents are handled at the extremes', () => {
    for (const id of ['warm', 'ember', 'slate', 'olive'] as const) {
      const palette = paletteTokens(id);
      expect(accentText('#000000', palette)).toBe('#000000');
      expect(
        worstRatio(accentText('#ffffff', palette), palette),
      ).toBeGreaterThanOrEqual(AA_BODY);
    }
    const midnight = paletteTokens('midnight');
    expect(accentText('#ffffff', midnight)).toBe('#ffffff');
    expect(
      worstRatio(accentText('#000000', midnight), midnight),
    ).toBeGreaterThanOrEqual(AA_BODY);
  });

  test('rounding edges near the extremes still conform', () => {
    for (const id of PALETTE_IDS) {
      const palette = paletteTokens(id);
      for (const accent of ['#010101', '#fefefe', '#000001', '#fffffe']) {
        expect(
          worstRatio(accentText(accent, palette), palette),
        ).toBeGreaterThanOrEqual(AA_BODY);
      }
    }
  });

  test('an invalid accent falls closed before the derivation sees it', () => {
    // `safeAccent` (accent.ts) is the gate; a 200 projection cannot carry
    // an invalid accent in the first place (backend validation).
    const warm = paletteTokens('warm');
    expect(accentText('expression(alert(1))', warm)).toBe(
      accentText('#a34b2a', warm),
    );
  });
});

describe('hue and saturation survive the lightness walk', () => {
  test('an adjusted token keeps the accent hue', () => {
    const midnight = paletteTokens('midnight');
    for (const accent of ['#a34b2a', '#0000cc', '#116611', '#8b1a5c']) {
      const derived = accentText(accent, midnight);
      expect(derived).not.toBe(accent);
      // Rounding to 8-bit channels moves the hue slightly; the identity
      // must survive, not be bit-exact.
      expect(Math.abs(hue(derived) - hue(accent))).toBeLessThan(3);
    }
  });
});

describe('determinism', () => {
  test('the same accent and palette always produce the same token', () => {
    for (const id of PALETTE_IDS) {
      const palette = paletteTokens(id);
      for (let r = 0; r <= 255; r += 51) {
        for (let g = 0; g <= 255; g += 51) {
          for (let b = 0; b <= 255; b += 51) {
            const accent = hex(r, g, b);
            expect(accentText(accent, palette)).toBe(
              accentText(accent, palette),
            );
          }
        }
      }
    }
  });
});

describe('the fallback branch', () => {
  // With the shipped palettes the fallback is unreachable - proved by the
  // termination assertions above. It is exercised by raising the floor
  // past the analytic ceiling of min(contrast vs black, contrast vs
  // white), which is ~4.58 (the same constant that bounds
  // `accentForeground`), on a straddling black/white surface pair. No
  // fabricated palette is needed, and the internal floor parameter is
  // deliberately absent from the package's public surface.
  const straddling: PaletteTokens = {
    bg: '#000000',
    surface: '#ffffff',
    text: '#767676',
    muted: '#767676',
    border: '#767676',
  };

  test('an impossible floor falls back to the palette text token', () => {
    expect(deriveAccentText('#0000ff', straddling, 4.6)).toBe(straddling.text);
    expect(deriveAccentText('#a34b2a', straddling, 4.6)).toBe(straddling.text);
  });

  test('the same inputs at the real floor still resolve by walking', () => {
    expect(deriveAccentText('#0000ff', straddling, AA_BODY)).not.toBe(
      straddling.text,
    );
  });
});
