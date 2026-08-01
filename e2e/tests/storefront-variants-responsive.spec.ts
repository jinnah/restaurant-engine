import { expect, test } from '@playwright/test';
import { seedPublishedStorefront } from '../support/api';
import { expectPageClean, watchPage } from '../support/hygiene';
import {
  expectHeadingsContained,
  expectImagesContained,
  expectNoPageOverflow,
  expectReadableText,
  expectSectionsStacked,
  expectTargetGeometry,
} from '../support/layout';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';
import {
  expectPalette,
  readTenantTokens,
  type DesignVariantId,
  type PaletteId,
} from '../support/theme';

/**
 * Per-variant responsive acceptance (M4G-D, ADR-024 §11).
 *
 * The same six ADR-023 viewports and the same geometric floors the
 * `classic` matrix already passes (`storefront-responsive.spec.ts`),
 * applied to the two variants M4G-B added. The floors themselves live in
 * `support/layout.ts` so both matrices assert one shared definition
 * rather than two drifting copies.
 *
 * `classic` is deliberately not repeated here: M4F already covers it at
 * these widths, and §12's combinatorial control exists precisely to stop
 * this matrix growing by multiplication.
 *
 * Semantic and geometric only — no screenshot baseline and no pixel gate.
 * Passing is evidence for these widths and this content, not proof of
 * support for every possible device.
 */

// The M4F automated viewport matrix (ADR-023), unchanged.
const VIEWPORTS = [
  { width: 320, height: 900 },
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
  { width: 1280, height: 900 },
];

// The captured subset, matching the M4F evidence convention.
const CAPTURE = new Set(['320x900', '390x844', '768x1024', '1280x900']);

const HERO_HEADING =
  'Slow-cooked classics and wood-fired specialties, served the way our ' +
  'grandparents taught us';
const HERO_SUBHEADING =
  'A neighborhood kitchen for long lunches, family dinners, and every ' +
  'celebration in between';
const STORY_BODY =
  'Three generations of one family have cooked in this building. The ' +
  'dining room still has its original pressed-tin ceiling, the tandoor ' +
  'was built by hand from river clay, and most of the recipes have never ' +
  'been written down — they are taught at the stove, one season at a ' +
  'time, to whoever is patient enough to learn them properly.';
const CATEGORY = 'House specialties';
const ITEM = 'Clay-oven lamb shank with saffron rice';
const IMAGE_ALT = 'The dining room set for dinner service';

const SECTION_HEADINGS = [
  HERO_HEADING,
  'From our kitchen',
  'Our story',
  'Visit us',
  'The dining room',
];

interface ResponsiveCase {
  variant: DesignVariantId;
  palette: PaletteId;
}

const CASES: ResponsiveCase[] = [
  { variant: 'editorial', palette: 'midnight' },
  { variant: 'express', palette: 'ember' },
];

for (const testCase of CASES) {
  // Spec-owned namespaces (ADR-019 D6). The business name is deliberately
  // long: name wrapping at narrow widths is part of what this proves.
  const ns = {
    ...specNamespace(`sf-resp-${testCase.variant}`),
    businessName: 'The Riverside Family Restaurant and Banquet Hall',
  };

  test(`the ${testCase.variant} storefront is responsive on both public routes at every supported width`, async ({
    browser,
  }) => {
    test.setTimeout(600_000);

    await seedPublishedStorefront(
      ns,
      {
        category: CATEGORY,
        item: ITEM,
        imageAlt: IMAGE_ALT,
        heroHeading: HERO_HEADING,
        heroSubheading: HERO_SUBHEADING,
        storyBody: STORY_BODY,
      },
      {
        variant: testCase.variant,
        logo: true,
        theme: { palette: testCase.palette },
      },
    );

    const context = await visitorContext(browser);
    try {
      const page = await context.newPage();
      const problems = watchPage(page);

      for (const viewport of VIEWPORTS) {
        const tag = `${String(viewport.width)}x${String(viewport.height)}`;
        const where = `${testCase.variant} ${tag}`;
        await page.setViewportSize(viewport);

        // --- Home ----------------------------------------------------
        const home = await publicVisit(page, storefrontOrigin(ns.slug));
        expect(home.status(), `home status at ${where}`).toBe(200);

        // The assigned variant survives every width — a responsive
        // breakpoint must never silently fall back to another layout.
        const tokens = await readTenantTokens(page);
        expect(tokens.variant, `variant at ${where}`).toBe(testCase.variant);
        await expectPalette(page, testCase.palette, `home ${where}`);

        await expect(
          page.getByRole('heading', { name: ns.businessName, level: 1 }),
        ).toBeVisible();
        await expect(page.locator('h1')).toHaveCount(1);

        // Section order and visibility are exactly the composition.
        await expect(page.getByRole('heading', { level: 2 })).toHaveText(
          SECTION_HEADINGS,
        );
        await expect(page.getByText(STORY_BODY)).toBeVisible();

        // Primary navigation and the primary public action are operable
        // at every width, and the target floor holds on the narrow ones.
        const nav = page.getByRole('navigation', { name: 'Site' });
        await expect(nav.getByRole('link', { name: 'Menu' })).toBeVisible();
        const cta = page.getByRole('link', { name: 'View menu', exact: true });
        await expect(cta).toBeVisible();
        await expectTargetGeometry(
          page,
          'nav[aria-label="Site"] a',
          `home ${where}`,
        );

        await expectNoPageOverflow(page, `home ${where}`);
        await expectHeadingsContained(page, `home ${where}`);
        await expectImagesContained(page, `home ${where}`);
        await expectSectionsStacked(page, `home ${where}`);
        await expectReadableText(page, 'main section p', `home ${where}`);

        if (CAPTURE.has(tag)) {
          await page.screenshot({
            path: `test-results/m4g-d-visual/${testCase.variant}-responsive-home-${tag}.png`,
            fullPage: true,
          });
        }

        // --- Menu, reached through the primary action ----------------
        await cta.click();
        await expect(
          page.getByRole('heading', { name: 'Menu', level: 2 }),
        ).toBeVisible();
        await expect(
          page.getByRole('heading', { name: CATEGORY, level: 3 }),
        ).toBeVisible();
        await expect(page.getByText(ITEM).first()).toBeVisible();
        await expect(page.getByText('$9.50').first()).toBeVisible();

        await expectNoPageOverflow(page, `menu ${where}`);
        await expectHeadingsContained(page, `menu ${where}`);
        await expectImagesContained(page, `menu ${where}`);
        await expectReadableText(page, 'main li p', `menu ${where}`);

        if (CAPTURE.has(tag)) {
          await page.screenshot({
            path: `test-results/m4g-d-visual/${testCase.variant}-responsive-menu-${tag}.png`,
            fullPage: true,
          });
        }
      }

      expectPageClean(problems, `${testCase.variant} responsive matrix`);
    } finally {
      await context.close();
    }
  });
}
