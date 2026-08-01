/**
 * The curated design surface, restated for browser acceptance (M4G-D,
 * ADR-024 §3/§5/§6).
 *
 * The registry values below are **deliberately duplicated** rather than
 * imported from `@restaurant-engine/storefront-renderer`. This suite is
 * black-box acceptance: it asserts what a browser actually computed
 * against the values ADR-024 publishes as the permanent contract. Reading
 * them from the same module the renderer renders from would make any
 * drift invisible — the assertion would follow the defect. The renderer's
 * own unit suites already pin the internal source; this pins the outcome.
 *
 * Adding the renderer as an e2e dependency would also be a dependency and
 * lockfile change, which M4G-D is not authorized to make.
 */

import { expect, type Page } from '@playwright/test';

export type DesignVariantId = 'classic' | 'editorial' | 'express';
export type PaletteId = 'warm' | 'ember' | 'slate' | 'olive' | 'midnight';
export type TypePairingId = 'humanist' | 'serif_display' | 'geometric';

export interface PaletteExpectation {
  readonly bg: string;
  readonly surface: string;
  readonly text: string;
  readonly muted: string;
  readonly border: string;
}

/** ADR-024 §3/§5: the five permanent palettes, as published. */
export const PALETTES: Record<PaletteId, PaletteExpectation> = {
  warm: {
    bg: '#faf8f5',
    surface: '#ffffff',
    text: '#241f1c',
    muted: '#5f574f',
    border: '#e0dad2',
  },
  ember: {
    bg: '#f4ece4',
    surface: '#fffaf5',
    text: '#2a1c14',
    muted: '#5d4636',
    border: '#ddc9b6',
  },
  slate: {
    bg: '#f4f6f8',
    surface: '#ffffff',
    text: '#1b2027',
    muted: '#525c68',
    border: '#d5dbe2',
  },
  olive: {
    bg: '#f4f5ee',
    surface: '#fdfdf8',
    text: '#1f2418',
    muted: '#535b45',
    border: '#d7dbc7',
  },
  midnight: {
    bg: '#14171c',
    surface: '#1e232a',
    text: '#f2f4f7',
    muted: '#adb6c2',
    border: '#333b45',
  },
};

/**
 * ADR-024 §6: the three permanent pairings. `scale` multiplies the
 * delivered 1.75rem h1, so the computed heading size is a deterministic
 * consequence of the selection and is asserted as one.
 */
export const TYPE_PAIRINGS: Record<
  TypePairingId,
  { readonly headingFirstFamily: string; readonly scale: number }
> = {
  humanist: { headingFirstFamily: 'system-ui', scale: 1 },
  serif_display: { headingFirstFamily: 'ui-serif', scale: 1.05 },
  geometric: { headingFirstFamily: 'Avenir Next', scale: 1.15 },
};

/**
 * The `h1` size each variant's own chrome declares, in px at the 16px
 * root, before the pairing's scale multiplies it.
 *
 * ADR-024 §8 gives a variant its own type scale and §6 gives the pairing
 * a unitless multiplier over it, so the rendered size is the product of
 * the two: `calc(<variant base> * var(--type-scale))`. Asserting that
 * product is what proves the pairing actually reached the heading through
 * the variant's chrome rather than stopping at the token.
 *
 * The shared `:where(.tenantPage) h1` rule sits at specificity (0,0,1)
 * deliberately so each variant's `.name` class overrides it — which is
 * why these bases, not the shared 1.75rem, are the ones that render.
 */
const VARIANT_H1_BASE_PX: Record<DesignVariantId, number> = {
  classic: 22, // 1.375rem
  editorial: 36, // 2.25rem
  express: 18, // 1.125rem
};

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

/**
 * Parse either form a browser hands back: custom properties keep their
 * authored `#rrggbb`, real properties compute to `rgb(r, g, b)`.
 */
export function parseCssColor(value: string): Rgb {
  const text = value.trim();
  const hex = /^#([0-9a-f]{6})$/i.exec(text);
  if (hex !== null) {
    const n = Number.parseInt(hex[1]!, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }
  const rgb = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(text);
  if (rgb !== null) {
    return {
      r: Math.round(Number(rgb[1])),
      g: Math.round(Number(rgb[2])),
      b: Math.round(Number(rgb[3])),
    };
  }
  throw new Error(`unparseable CSS colour: ${JSON.stringify(value)}`);
}

function channel(value: number): number {
  const s = value / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

/** WCAG 2.x relative luminance. */
export function relativeLuminance(c: Rgb): number {
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
}

/** WCAG 2.x contrast ratio, restated independently of the renderer. */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** The AA body-text floor ADR-024 §5 derives `--accent-text` against. */
export const AA_BODY = 4.5;

export interface TenantTokens {
  variant: string;
  motion: string | null;
  colorBg: string;
  colorSurface: string;
  colorText: string;
  colorMuted: string;
  colorBorder: string;
  accent: string;
  accentText: string;
  accentContrast: string;
  fontHeading: string;
  typeScale: string;
  /** The painted background of the element `themeStyle()` was applied to. */
  themedBackground: string;
  /** Whether that element is `<body>` — true on the public storefront. */
  themedIsBody: boolean;
}

/**
 * Read the theme as the browser resolved it.
 *
 * Token values are read through `[data-variant]` — the variant root —
 * because custom properties inherit down from the `.tenantPage` boundary
 * where `themeStyle()` applies them (M4G-B).
 *
 * The *painted* background is read from the themed element itself, found
 * by the inline custom property `themeStyle()` writes. That element is
 * `<body>` on the public storefront and the preview container in the
 * control center — M4G-B's deliberate two-site application — so locating
 * it this way lets one helper serve both surfaces honestly instead of
 * assuming `<body>` and silently measuring the control center's own
 * chrome in preview.
 */
export async function readTenantTokens(page: Page): Promise<TenantTokens> {
  return page.evaluate(() => {
    const root = document.querySelector('[data-variant]');
    if (root === null) {
      throw new Error('no [data-variant] root found on the page');
    }
    const themed = document.querySelector('[style*="--color-bg"]');
    if (themed === null) {
      throw new Error('no element carrying the themeStyle custom properties');
    }
    const style = getComputedStyle(root);
    const read = (name: string) => style.getPropertyValue(name).trim();
    return {
      variant: root.getAttribute('data-variant') ?? '',
      motion: root.getAttribute('data-motion'),
      colorBg: read('--color-bg'),
      colorSurface: read('--color-surface'),
      colorText: read('--color-text'),
      colorMuted: read('--color-muted'),
      colorBorder: read('--color-border'),
      accent: read('--accent'),
      accentText: read('--accent-text'),
      accentContrast: read('--accent-contrast'),
      fontHeading: read('--font-heading'),
      typeScale: read('--type-scale'),
      themedBackground: getComputedStyle(themed).backgroundColor,
      themedIsBody: themed === document.body,
    };
  });
}

/**
 * The palette reached the browser: all five tokens, and the themed
 * element actually paints its background colour rather than merely
 * declaring the token. Valid on both the public storefront and the
 * authenticated preview.
 */
export async function expectPalette(
  page: Page,
  palette: PaletteId,
  where: string,
): Promise<void> {
  const expected = PALETTES[palette];
  const tokens = await readTenantTokens(page);
  expect(tokens.colorBg, `--color-bg at ${where}`).toBe(expected.bg);
  expect(tokens.colorSurface, `--color-surface at ${where}`).toBe(
    expected.surface,
  );
  expect(tokens.colorText, `--color-text at ${where}`).toBe(expected.text);
  expect(tokens.colorMuted, `--color-muted at ${where}`).toBe(expected.muted);
  expect(tokens.colorBorder, `--color-border at ${where}`).toBe(
    expected.border,
  );
  expect(
    parseCssColor(tokens.themedBackground),
    `painted themed surface at ${where}`,
  ).toEqual(parseCssColor(expected.bg));
}

/**
 * Public surface only: the themed element IS `<body>`, so the palette
 * reaches the painted browser canvas.
 *
 * This is the specific outcome M4G-B's recorded application-site decision
 * exists to secure — tokens on a descendant would leave a light canvas
 * behind a `midnight` page — so it is asserted in a real browser rather
 * than trusted from the stylesheet.
 */
export async function expectPaintedCanvas(
  page: Page,
  palette: PaletteId,
  where: string,
): Promise<void> {
  const tokens = await readTenantTokens(page);
  expect(
    tokens.themedIsBody,
    `the public storefront must apply the theme at <body> (${where})`,
  ).toBe(true);
  const bodyBackground = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  expect(
    parseCssColor(bodyBackground),
    `painted <body> canvas at ${where}`,
  ).toEqual(parseCssColor(PALETTES[palette].bg));
}

/**
 * The pairing reached the browser: the token carries the registered
 * scale, the heading stack leads with the pairing's own family, and the
 * rendered `h1` is the variant's own base multiplied by that scale.
 */
export async function expectTypePairing(
  page: Page,
  pairing: TypePairingId,
  where: string,
): Promise<void> {
  const expected = TYPE_PAIRINGS[pairing];
  const tokens = await readTenantTokens(page);
  expect(tokens.typeScale, `--type-scale at ${where}`).toBe(
    String(expected.scale),
  );
  expect(
    tokens.fontHeading.replace(/['"]/g, ''),
    `--font-heading leads with the pairing family at ${where}`,
  ).toContain(expected.headingFirstFamily);

  const heading = await page
    .locator('h1')
    .first()
    .evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        fontSize: Number.parseFloat(style.fontSize),
        fontFamily: style.fontFamily,
      };
    });

  // The pairing's heading stack is what the heading actually resolves to,
  // not merely what the token holds.
  expect(
    heading.fontFamily.replace(/['"]/g, ''),
    `rendered h1 font-family at ${where}`,
  ).toContain(expected.headingFirstFamily);

  const variant = tokens.variant as DesignVariantId;
  const base = VARIANT_H1_BASE_PX[variant];
  expect(base, `unknown variant "${variant}" at ${where}`).toBeDefined();
  expect(heading.fontSize, `computed h1 size at ${where}`).toBeCloseTo(
    base * expected.scale,
    1,
  );
}

/**
 * ADR-024 §5: `--accent-text` is the contrast-guarded token every
 * text/focus use reads. Whatever the derivation produced, the browser must
 * end up with something that clears the AA body floor against both the
 * page background and the raised surface — that is the whole point of the
 * token, asserted on the value the browser actually resolved.
 */
export async function expectAccentTextLegible(
  page: Page,
  palette: PaletteId,
  where: string,
): Promise<void> {
  const tokens = await readTenantTokens(page);
  const accentText = parseCssColor(tokens.accentText);
  for (const [name, against] of [
    ['background', PALETTES[palette].bg],
    ['surface', PALETTES[palette].surface],
  ] as const) {
    const ratio = contrastRatio(accentText, parseCssColor(against));
    expect(
      ratio,
      `--accent-text (${tokens.accentText}) against the ${palette} ${name} at ${where}`,
    ).toBeGreaterThanOrEqual(AA_BODY);
  }
}
