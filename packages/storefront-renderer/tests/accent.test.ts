// @vitest-environment node

// The platform accessibility floor for the tenant accent (ADR-021): the
// black-or-white foreground choice must clear WCAG AA (4.5:1) against
// EVERY possible accent, not just pleasant ones. That is asserted across
// a dense sample of the sRGB cube plus the analytic worst case, so the
// guarantee is measured rather than trusted.

import { describe, expect, test } from 'vitest';

import {
  accentForeground,
  contrastRatio,
  DEFAULT_ACCENT,
  isValidAccent,
  relativeLuminance,
  safeAccent,
} from '../src/accent';

function hex(r: number, g: number, b: number): string {
  const part = (v: number) => v.toString(16).padStart(2, '0');
  return `#${part(r)}${part(g)}${part(b)}`;
}

describe('accent validation', () => {
  test('accepts exactly the backend accent shape', () => {
    expect(isValidAccent('#a34b2a')).toBe(true);
    expect(isValidAccent('#A34B2A')).toBe(false);
    expect(isValidAccent('#abc')).toBe(false);
    expect(isValidAccent('a34b2a')).toBe(false);
    expect(isValidAccent('#a34b2g')).toBe(false);
  });

  test('an invalid value falls closed to the platform default', () => {
    expect(safeAccent('#a34b2a')).toBe('#a34b2a');
    expect(safeAccent('url(javascript:1)')).toBe(DEFAULT_ACCENT);
    expect(safeAccent('')).toBe(DEFAULT_ACCENT);
  });
});

describe('relative luminance', () => {
  test('matches the WCAG anchors', () => {
    expect(relativeLuminance('#000000')).toBe(0);
    expect(relativeLuminance('#ffffff')).toBeCloseTo(1, 10);
    // sRGB mid gray, the standard published value.
    expect(relativeLuminance('#808080')).toBeCloseTo(0.21586, 4);
  });
});

describe('accentForeground', () => {
  test('chooses white on dark accents and black on light accents', () => {
    expect(accentForeground('#000000')).toBe('#ffffff');
    expect(accentForeground('#1a1a2e')).toBe('#ffffff');
    expect(accentForeground('#ffffff')).toBe('#000000');
    expect(accentForeground('#ffe97a')).toBe('#000000');
  });

  test('guarantees at least 4.5:1 across the sRGB cube (dense sample)', () => {
    let worst = Number.POSITIVE_INFINITY;
    for (let r = 0; r <= 255; r += 17) {
      for (let g = 0; g <= 255; g += 17) {
        for (let b = 0; b <= 255; b += 17) {
          const accent = hex(r, g, b);
          const luminance = relativeLuminance(accent);
          const foreground = accentForeground(accent);
          const ratio = contrastRatio(
            luminance,
            foreground === '#000000' ? 0 : 1,
          );
          worst = Math.min(worst, ratio);
          expect(ratio).toBeGreaterThanOrEqual(4.5);
        }
      }
    }
    // The analytic worst case is ≈4.58; the sampled worst must sit there.
    expect(worst).toBeGreaterThanOrEqual(4.5);
    expect(worst).toBeLessThan(5);
  });
});
