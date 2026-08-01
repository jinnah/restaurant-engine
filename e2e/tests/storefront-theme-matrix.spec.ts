import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { seedPublishedStorefront } from '../support/api';
import { expectPageClean, watchPage } from '../support/hygiene';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';
import {
  expectAccentTextLegible,
  expectPalette,
  expectTypePairing,
  readTenantTokens,
} from '../support/theme';

/**
 * The remainder of the pairwise palette × pairing selection, and the two
 * §7 logo-absence branches (M4G-D, ADR-024 §7/§11/§12).
 *
 * `storefront-variants.spec.ts` covers warm/midnight/ember against all
 * three pairings; this file covers the two remaining palettes, so every
 * registered palette and every registered pairing is proved in a real
 * browser across five combinations rather than the fifteen-cell product
 * §12 forbids.
 *
 * Both cases also carry a logo *absence*, which is where §7's fallback
 * ruling lives: nothing is missing from the page when the logo is not
 * there, because the business name is always the visible `h1` and the
 * image conveys nothing on its own.
 */

const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

const CATEGORY = 'House specialties';
const ITEM = 'Clay-oven lamb shank';
const IMAGE_ALT = 'The dining room set for dinner service';
const HERO_SUBHEADING = 'A neighborhood kitchen with a wood-fired oven';
const STORY_BODY =
  'The kitchen has been in one family for three generations, and the ' +
  'oven at its center was built by hand before the first table was set.';

async function expectNoAxeViolations(page: Page, where: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  const report = results.violations.map((violation) => ({
    rule: violation.id,
    impact: violation.impact,
    help: violation.help,
    targets: violation.nodes.map((node) => node.target),
  }));
  expect(
    report,
    `axe violations at ${where}:\n${JSON.stringify(report, null, 2)}`,
  ).toEqual([]);
}

const nsNoLogo = specNamespace('sf-theme-slate');
const nsBrokenLogo = specNamespace('sf-theme-olive');

test('the slate palette renders with humanist typography and name-only chrome when no logo is set', async ({
  browser,
}) => {
  test.setTimeout(300_000);

  await seedPublishedStorefront(
    nsNoLogo,
    {
      category: CATEGORY,
      item: ITEM,
      imageAlt: IMAGE_ALT,
      heroHeading: 'Cool mornings, long lunches',
      heroSubheading: HERO_SUBHEADING,
      storyBody: STORY_BODY,
    },
    {
      variant: 'classic',
      // No `logo: true` — theme.logo stays null, which is the delivered
      // pre-M4G shape and the §7 "absent reference" branch.
      theme: { palette: 'slate', typePairing: 'humanist', accent: '#1f4f8f' },
    },
  );

  const context = await visitorContext(browser);
  try {
    const page = await context.newPage();
    const problems = watchPage(page);

    const home = await publicVisit(page, storefrontOrigin(nsNoLogo.slug));
    expect(home.status()).toBe(200);

    await expectPalette(page, 'slate', 'slate /');
    await expectTypePairing(page, 'humanist', 'slate /');
    await expectAccentTextLegible(page, 'slate', 'slate /');

    // §7: name-only chrome. No fabricated frame, no placeholder, no
    // broken-image icon — the header simply carries the name.
    await expect(
      page.locator('header img'),
      'no logo image is rendered when none is set',
    ).toHaveCount(0);
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(
      page.getByRole('heading', { name: nsNoLogo.businessName, level: 1 }),
    ).toBeVisible();

    await expectNoAxeViolations(page, 'slate / (no logo)');
    expectPageClean(problems, 'slate / (no logo)');
  } finally {
    await context.close();
  }
});

test('the olive palette renders with geometric typography and survives a logo whose bytes never arrive', async ({
  browser,
}) => {
  test.setTimeout(300_000);

  const { logoMediaId } = await seedPublishedStorefront(
    nsBrokenLogo,
    {
      category: CATEGORY,
      item: ITEM,
      imageAlt: IMAGE_ALT,
      heroHeading: 'Everything from the garden',
      heroSubheading: HERO_SUBHEADING,
      storyBody: STORY_BODY,
    },
    {
      variant: 'express',
      logo: true,
      theme: { palette: 'olive', typePairing: 'geometric', accent: '#3f6b1f' },
    },
  );
  expect(logoMediaId, 'the fixture staged a logo').toBeDefined();

  const context = await visitorContext(browser);
  try {
    const page = await context.newPage();
    const problems = watchPage(page);

    // §7: "a reference the viewer's browser fails to load costs nothing
    // informational". Simulated at the transport layer — the product is
    // untouched, and only this one asset is refused.
    await page.route(
      (url) => url.pathname.includes(logoMediaId!),
      async (route) => {
        await route.abort('failed');
      },
    );

    const home = await publicVisit(page, storefrontOrigin(nsBrokenLogo.slug));
    expect(home.status()).toBe(200);

    await expectPalette(page, 'olive', 'olive /');
    await expectTypePairing(page, 'geometric', 'olive /');
    await expectAccentTextLegible(page, 'olive', 'olive /');

    const tokens = await readTenantTokens(page);
    expect(tokens.variant, 'olive case variant').toBe('express');

    // The logo element is still in the document with its reserved box and
    // its empty alt, and it delivered nothing — which is exactly the
    // condition §7 rules costs nothing.
    const logo = page.locator('header img');
    await expect(logo).toHaveCount(1);
    expect(await logo.getAttribute('alt')).toBe('');
    const naturalWidth = await logo.evaluate(
      (el) => (el as HTMLImageElement).naturalWidth,
    );
    expect(naturalWidth, 'the aborted logo delivered no bytes').toBe(0);

    // The informational content is unaffected: the name is present as
    // text, the heading structure is intact, and the page still passes.
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(
      page.getByRole('heading', { name: nsBrokenLogo.businessName, level: 1 }),
    ).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Site' })).toBeVisible();
    await expectNoAxeViolations(page, 'olive / (logo bytes refused)');

    // The refusal this test itself performed is the ONLY problem the page
    // is allowed to report, and it is excluded by the exact media id
    // rather than by a blanket allowance — anything else still fails.
    const causedByRefusedLogo = (entry: string) => entry.includes(logoMediaId!);
    expect(
      problems.failedRequests.filter((e) => !causedByRefusedLogo(e)),
      'no transport failure other than the refused logo',
    ).toEqual([]);
    expect(
      problems.consoleErrors.filter((e) => !causedByRefusedLogo(e)),
      'no console error other than the refused logo',
    ).toEqual([]);
    // The refusal must genuinely have been observed, so this test cannot
    // pass by silently failing to intercept anything.
    expect(
      problems.failedRequests.filter(causedByRefusedLogo).length,
      'the logo refusal actually happened',
    ).toBeGreaterThan(0);
    expect(problems.pageErrors, 'no uncaught page errors').toEqual([]);
    expect(problems.serverErrors, 'no server errors').toEqual([]);
    expect(problems.clientErrors, 'no 4xx responses').toEqual([]);
  } finally {
    await context.close();
  }
});
