/**
 * Geometric layout floors, shared by every responsive acceptance spec.
 *
 * These were authored for the M4F `classic` matrix (ADR-023) and are moved
 * here unchanged by M4G-D so the per-variant matrix asserts *the same*
 * floors rather than a re-typed approximation of them. Semantic and
 * geometric only — no screenshot baseline and no pixel gate (ADR-023).
 */

import { expect, type Page } from '@playwright/test';

/** The document itself must not scroll sideways (ADR-019 D3 rationale). */
export async function expectNoPageOverflow(
  page: Page,
  where: string,
): Promise<void> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(
    scrollWidth,
    `page scrolls horizontally at ${where} (${String(scrollWidth)} > ${String(clientWidth)})`,
  ).toBeLessThanOrEqual(clientWidth);
}

/** Every rendered image sits inside the viewport and kept real bytes. */
export async function expectImagesContained(
  page: Page,
  where: string,
): Promise<void> {
  const images = await page.evaluate(() => {
    const clientWidth = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll('img')).map((img) => {
      const rect = img.getBoundingClientRect();
      return {
        alt: img.alt,
        left: rect.left,
        right: rect.right,
        width: rect.width,
        height: rect.height,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight,
        clientWidth,
      };
    });
  });
  for (const img of images) {
    expect(
      img.right,
      `image "${img.alt}" overflows the viewport at ${where}`,
    ).toBeLessThanOrEqual(img.clientWidth + 1);
    expect(
      img.left,
      `image "${img.alt}" starts left of the viewport at ${where}`,
    ).toBeGreaterThanOrEqual(-1);
    expect(
      img.naturalWidth,
      `image "${img.alt}" has no delivered bytes at ${where}`,
    ).toBeGreaterThan(0);
    expect(
      img.width,
      `image "${img.alt}" collapsed at ${where}`,
    ).toBeGreaterThan(0);
    // Proportion sanity, not pixel styling: a displayed shape wildly off
    // the intrinsic one (flattened or stretched several times over)
    // means the layout broke. Deliberate object-fit crops sit well
    // inside this band.
    const intrinsic = img.naturalWidth / img.naturalHeight;
    const displayed = img.width / img.height;
    expect(
      Math.abs(displayed - intrinsic) / intrinsic,
      `image "${img.alt}" is grossly distorted at ${where}`,
    ).toBeLessThan(1.5);
  }
}

/** Headings render fully inside the horizontal viewport (no clipping). */
export async function expectHeadingsContained(
  page: Page,
  where: string,
): Promise<void> {
  const headings = await page.evaluate(() => {
    const clientWidth = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll('h1, h2, h3')).map((el) => {
      const rect = el.getBoundingClientRect();
      return {
        text: (el.textContent ?? '').slice(0, 40),
        left: rect.left,
        right: rect.right,
        height: rect.height,
        clientWidth,
      };
    });
  });
  for (const heading of headings) {
    expect(
      heading.right,
      `heading "${heading.text}" clips off-screen at ${where}`,
    ).toBeLessThanOrEqual(heading.clientWidth + 1);
    expect(
      heading.left,
      `heading "${heading.text}" starts off-screen at ${where}`,
    ).toBeGreaterThanOrEqual(-1);
    expect(
      heading.height,
      `heading "${heading.text}" collapsed at ${where}`,
    ).toBeGreaterThan(0);
  }
}

/** Sections stack without overlapping one another. */
export async function expectSectionsStacked(
  page: Page,
  where: string,
): Promise<void> {
  const boxes = await page.evaluate(() =>
    Array.from(document.querySelectorAll('main section')).map((el) => {
      const rect = el.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom };
    }),
  );
  const sorted = [...boxes].sort((a, b) => a.top - b.top);
  for (let i = 1; i < sorted.length; i += 1) {
    expect(
      sorted[i]!.top,
      `sections overlap at ${where}`,
    ).toBeGreaterThanOrEqual(sorted[i - 1]!.bottom - 1);
  }
}

/** Body text stays readable without zooming (a floor, not a design). */
export async function expectReadableText(
  page: Page,
  selector: string,
  where: string,
): Promise<void> {
  const fontSize = await page
    .locator(selector)
    .first()
    .evaluate((el) => Number.parseFloat(getComputedStyle(el).fontSize));
  expect(
    fontSize,
    `text at ${selector} is below the 14px readability floor at ${where}`,
  ).toBeGreaterThanOrEqual(14);
}

/**
 * ADR-024 §11: the 44px interactive-target floor, pinned per variant in a
 * real browser rather than from a stylesheet declaration.
 */
export async function expectTargetGeometry(
  page: Page,
  selector: string,
  where: string,
): Promise<void> {
  const box = await page.locator(selector).first().boundingBox();
  expect(box, `no box for ${selector} at ${where}`).not.toBeNull();
  expect(
    box!.height,
    `${selector} is below the 44px target floor at ${where}`,
  ).toBeGreaterThanOrEqual(44);
  expect(
    box!.width,
    `${selector} is below the 44px target floor at ${where}`,
  ).toBeGreaterThanOrEqual(44);
}
