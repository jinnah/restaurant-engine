import { expect, test } from '@playwright/test';
import { seedPublishedStorefront } from '../support/api';
import {
  expectHeadingsContained,
  expectImagesContained,
  expectNoPageOverflow,
  expectReadableText,
  expectSectionsStacked,
} from '../support/layout';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';

// Spec-owned namespace (ADR-019 D6). The business name is deliberately
// long and realistic: name wrapping at narrow widths is part of what
// this spec exists to prove, and a short fixture name would prove
// nothing about it.
const ns = {
  ...specNamespace('sf-resp'),
  businessName: 'The Riverside Family Restaurant and Banquet Hall',
};

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

// The M4F automated viewport matrix (ADR-023): the M3-era 320/375/768
// phone-and-tablet widths plus current common phone geometries and the
// desktop baseline the visual procedures already use.
const VIEWPORTS = [
  { width: 320, height: 900 },
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
  { width: 1280, height: 900 },
];

// The subset captured as disposable manual-inspection evidence
// (screenshots land in the gitignored test-results directory; they are
// verification evidence, never committed baselines or pixel gates).
const CAPTURE = new Set(['320x900', '390x844', '768x1024', '1280x900']);

const SECTION_HEADINGS = [
  HERO_HEADING,
  'From our kitchen',
  'Our story',
  'Visit us',
  'The dining room',
];

/**
 * Responsive acceptance for the production-renderable `classic`
 * storefront (M4F, ADR-023): both public routes at every supported
 * width, through real browser geometry — semantic and geometric
 * assertions only, no screenshot baseline and no pixel gate. Passing
 * this matrix is evidence for these widths and this content, not proof
 * of support for every possible device.
 */
test('the classic storefront is responsive on both public routes at every supported width', async ({
  browser,
}) => {
  test.setTimeout(420_000);

  await seedPublishedStorefront(ns, {
    category: CATEGORY,
    item: ITEM,
    imageAlt: IMAGE_ALT,
    heroHeading: HERO_HEADING,
    heroSubheading: HERO_SUBHEADING,
    storyBody: STORY_BODY,
  });

  const context = await visitorContext(browser);
  try {
    const page = await context.newPage();

    for (const viewport of VIEWPORTS) {
      const tag = `${String(viewport.width)}x${String(viewport.height)}`;
      await page.setViewportSize(viewport);

      // --- Home ------------------------------------------------------
      const home = await publicVisit(page, storefrontOrigin(ns.slug));
      expect(home.status(), `home status at ${tag}`).toBe(200);

      // Tenant identity: resolved from the host, visible, unclipped.
      await expect(
        page.getByRole('heading', { name: ns.businessName, level: 1 }),
      ).toBeVisible();

      // Section order and visibility are exactly the composition.
      await expect(page.getByRole('heading', { level: 2 })).toHaveText(
        SECTION_HEADINGS,
      );
      await expect(page.getByText(STORY_BODY)).toBeVisible();

      // Primary navigation and the primary public action are operable.
      const nav = page.getByRole('navigation', { name: 'Site' });
      await expect(nav.getByRole('link', { name: 'Menu' })).toBeVisible();
      const cta = page.getByRole('link', { name: 'View menu', exact: true });
      await expect(cta).toBeVisible();

      await expectNoPageOverflow(page, `home ${tag}`);
      await expectHeadingsContained(page, `home ${tag}`);
      await expectImagesContained(page, `home ${tag}`);
      await expectSectionsStacked(page, `home ${tag}`);
      await expectReadableText(page, 'main section p', `home ${tag}`);

      if (CAPTURE.has(tag)) {
        await page.screenshot({
          path: `test-results/m4f-visual/home-${tag}.png`,
          fullPage: true,
        });
      }

      // --- Menu, reached through the primary action ------------------
      await cta.click();
      await expect(
        page.getByRole('heading', { name: 'Menu', level: 2 }),
      ).toBeVisible();
      await expect(
        page.getByRole('heading', { name: CATEGORY, level: 3 }),
      ).toBeVisible();
      await expect(page.getByText(ITEM).first()).toBeVisible();
      await expect(page.getByText('$9.50').first()).toBeVisible();

      await expectNoPageOverflow(page, `menu ${tag}`);
      await expectHeadingsContained(page, `menu ${tag}`);
      await expectImagesContained(page, `menu ${tag}`);
      await expectReadableText(page, 'main li p', `menu ${tag}`);

      if (CAPTURE.has(tag)) {
        await page.screenshot({
          path: `test-results/m4f-visual/menu-${tag}.png`,
          fullPage: true,
        });
      }
    }
  } finally {
    await context.close();
  }
});
