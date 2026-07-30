import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { seedPublishedStorefront } from '../support/api';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';
import { signIn } from '../support/ui';

// Spec-owned namespace (ADR-019 D6): one published five-section
// storefront — the smallest deterministic fixture that exercises every
// registered section type. Publication seeds the next draft from the
// published result, so the composer, preview, history, and version
// detail all have real state to present.
const ns = specNamespace('sf-a11y');

const HERO_HEADING = 'Wood-fired cooking, all seasons';
const HERO_SUBHEADING = 'A neighborhood kitchen with a wood-fired oven';
const STORY_BODY =
  'The kitchen has been in one family for three generations, and the ' +
  'oven at its center was built by hand before the first table was set.';
const CATEGORY = 'House specialties';
const ITEM = 'Clay-oven lamb shank';
const IMAGE_ALT = 'The dining room set for dinner service';

// The approved automated rule boundary (ADR-023): WCAG 2.0/2.1 A and AA
// rules, blocking at zero violations, with no blanket exclusions. A pass
// is engineering evidence within this boundary — it is not WCAG
// certification, not complete accessibility compliance, and not proof
// that no accessibility defects exist.
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/** Run axe and fail with a readable, target-bearing report. */
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

test('the public storefront pages pass the axe A/AA boundary with sound structure', async ({
  browser,
}) => {
  test.setTimeout(300_000);
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

    // --- Published public home -------------------------------------
    const home = await publicVisit(page, storefrontOrigin(ns.slug));
    expect(home.status()).toBe(200);
    await expect(
      page.getByRole('heading', { name: ns.businessName, level: 1 }),
    ).toBeVisible();
    await expectNoAxeViolations(page, 'public /');

    // Structure the scan does not judge: exactly one h1, and the four
    // landmark regions the layout commits to (ADR-021 §10).
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Site' })).toBeVisible();
    await expect(page.locator('main')).toHaveCount(1);
    await expect(page.getByRole('contentinfo')).toBeVisible();

    // Keyboard reachability: tabbing from the top of the document
    // reaches the primary navigation link.
    await page.locator('body').press('Tab');
    await expect(
      page.getByRole('navigation', { name: 'Site' }).getByRole('link'),
    ).toBeFocused();

    // --- Published public menu ---------------------------------------
    const menu = await publicVisit(page, `${storefrontOrigin(ns.slug)}/menu`);
    expect(menu.status()).toBe(200);
    await expect(
      page.getByRole('heading', { name: 'Menu', level: 2 }),
    ).toBeVisible();
    await expectNoAxeViolations(page, 'public /menu');
    await expect(page.locator('h1')).toHaveCount(1);
  } finally {
    await context.close();
  }
});

test('the storefront workspace pages pass the axe A/AA boundary with working dialog focus', async ({
  page,
}) => {
  test.setTimeout(300_000);
  const nsWorkspace = specNamespace('sf-a11y-ws');
  const { businessId } = await seedPublishedStorefront(nsWorkspace, {
    category: CATEGORY,
    item: ITEM,
    imageAlt: IMAGE_ALT,
    heroHeading: HERO_HEADING,
    heroSubheading: HERO_SUBHEADING,
    storyBody: STORY_BODY,
  });

  await signIn(page, nsWorkspace.ownerEmail, nsWorkspace.ownerPassword);

  // --- Overview + composer -------------------------------------------
  await page.goto(`/businesses/${businessId}/storefront`);
  await expect(
    page.getByRole('heading', { name: 'Storefront', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Version 1 —/)).toBeVisible();
  await expectNoAxeViolations(page, 'workspace overview/composer');

  // --- Composer with the section-edit dialog open ---------------------
  const editHero = page.getByRole('button', { name: 'Edit Hero' });
  await editHero.click();
  const dialog = page.getByRole('dialog', { name: 'Hero section' });
  await expect(dialog).toBeVisible();
  // Focus lands inside the dialog on open (real browser focus — the
  // part jsdom could not prove), and Escape closes it and returns
  // focus to the invoking control.
  await expect
    .poll(async () =>
      dialog.evaluate((el) => el.contains(document.activeElement)),
    )
    .toBe(true);
  await expectNoAxeViolations(page, 'composer with section-edit dialog open');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(editHero).toBeFocused();

  // --- Saved-draft preview --------------------------------------------
  await page.goto(`/businesses/${businessId}/storefront/preview`);
  await expect(
    page.getByRole('heading', { name: 'Storefront preview' }),
  ).toBeVisible();
  await expect(page.getByText(HERO_HEADING)).toBeVisible();
  await expectNoAxeViolations(page, 'saved-draft preview');

  // --- History ---------------------------------------------------------
  await page.goto(`/businesses/${businessId}/storefront/history`);
  await expect(
    page.getByRole('heading', { name: 'Storefront history' }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Version 1', exact: true }),
  ).toBeVisible();
  await expectNoAxeViolations(page, 'history');

  // --- Version detail --------------------------------------------------
  await page.getByRole('link', { name: 'Version 1', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Version 1 (published)' }),
  ).toBeVisible();
  await expectNoAxeViolations(page, 'version detail');
});
