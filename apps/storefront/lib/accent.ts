// Tenant accent handling with a platform-controlled accessibility floor
// (ADR-021; blueprint §12.3/§12.4).
//
// The accent is the whole of the tenant's styling surface — one validated
// `#rrggbb` token. It may decorate freely, but wherever it becomes a text
// background the foreground is chosen here, black or white by WCAG
// relative luminance. That choice is mathematically sufficient: the
// worse-cased better contrast of black-or-white over any sRGB color is
// ≈4.58:1 (at background luminance L where (L+0.05)² = 0.0525), which
// clears the 4.5:1 AA floor — a property the test suite asserts across
// the color space rather than trusts.
//
// Accent values arrive backend-validated (a 200 projection cannot carry an
// invalid accent), so an invalid value here is contract drift; it falls
// closed to the platform default rather than reaching CSS.

const ACCENT_PATTERN = /^#[0-9a-f]{6}$/;

/** The platform default accent (the backend's `DEFAULT_ACCENT`). */
export const DEFAULT_ACCENT = '#a34b2a';

export function isValidAccent(value: string): boolean {
  return ACCENT_PATTERN.test(value);
}

/** A syntactically safe accent for CSS: the value, or the default. */
export function safeAccent(value: string): string {
  return isValidAccent(value) ? value : DEFAULT_ACCENT;
}

function channel(linear: number): number {
  const scaled = linear / 255;
  return scaled <= 0.04045
    ? scaled / 12.92
    : Math.pow((scaled + 0.055) / 1.055, 2.4);
}

/** WCAG relative luminance of a `#rrggbb` color, in [0, 1]. */
export function relativeLuminance(accent: string): number {
  const value = safeAccent(accent);
  const r = channel(Number.parseInt(value.slice(1, 3), 16));
  const g = channel(Number.parseInt(value.slice(3, 5), 16));
  const b = channel(Number.parseInt(value.slice(5, 7), 16));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two luminances, in [1, 21]. */
export function contrastRatio(l1: number, l2: number): number {
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * The text color to use over an accent background: black or white,
 * whichever contrasts more (always ≥ 4.5:1 against any sRGB accent).
 */
export function accentForeground(accent: string): '#000000' | '#ffffff' {
  const luminance = relativeLuminance(accent);
  const withBlack = contrastRatio(luminance, 0);
  const withWhite = contrastRatio(luminance, 1);
  return withBlack >= withWhite ? '#000000' : '#ffffff';
}
