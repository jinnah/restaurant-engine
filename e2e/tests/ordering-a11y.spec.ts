import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { seedOrderingStorefront } from '../support/api';
import { expectNoPageOverflow, expectTargetGeometry } from '../support/layout';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { visitorContext } from '../support/publicApi';

/**
 * Responsive and accessibility acceptance for the ordering surfaces
 * (M6D, ADR-026; the blueprint §3.8/§12.4 floors as acceptance
 * criteria): the picker dialog, the checkout form with content, and the
 * tracker — scanned at the approved automated rule boundary and held to
 * the 44px target and no-horizontal-scroll floors at a mobile and a
 * desktop viewport.
 */

const ns = specNamespace('ordering-a11y');

const CONTENT = {
  category: 'Tandoor mains',
  item: 'Charcoal chicken plate',
  imageAlt: 'A charcoal-grilled chicken plate',
  heroHeading: 'Dinner, ready when you are',
  heroSubheading: 'Order ahead and pick up at the counter',
  storyBody:
    'The charcoal grill runs from first light to close, and the menu ' +
    'follows whatever the market had that morning.',
};

// The approved automated rule boundary (ADR-023): WCAG 2.0/2.1 A and AA,
// blocking at zero violations, no blanket exclusions.
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

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

const VIEWPORTS = [
  { label: 'mobile', width: 375, height: 812 },
  { label: 'desktop', width: 1280, height: 800 },
];

test('the ordering surfaces pass the axe boundary and hold the layout floors', async ({
  browser,
}) => {
  test.setTimeout(300_000);
  await seedOrderingStorefront(ns, CONTENT);
  const origin = storefrontOrigin(ns.slug);
  const context = await visitorContext(browser);
  const page = await context.newPage();

  // --- The picker, open, with the menu behind it.
  await page.goto(`${origin}/menu`);
  await page.getByRole('button', { name: 'Add to order' }).click();
  const dialog = page.getByRole('dialog', { name: CONTENT.item });
  await expect(dialog).toBeVisible();
  await expectNoAxeViolations(page, '/menu with the picker open');
  await expectTargetGeometry(
    page,
    'button[aria-label="Increase quantity"]',
    'the picker quantity control',
  );
  await dialog.getByRole('radio', { name: /Full/ }).check();
  await dialog.getByRole('button', { name: /^Add 1/ }).click();

  // --- Checkout, with a real line, across both viewports.
  await page.getByRole('link', { name: 'View order (1)' }).click();
  await expect(page.getByRole('heading', { name: 'Your order' })).toBeVisible();
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await expectNoPageOverflow(page, `/order at ${viewport.label}`);
  }
  await expectNoAxeViolations(page, '/order with cart content');
  await expectTargetGeometry(page, '#checkout-name', 'the checkout name field');

  // Both consents render unchecked — never pre-checked (D7), asserted
  // where the axe scan already proved the labels are real labels.
  for (const consent of await page.getByRole('checkbox').all()) {
    await expect(consent).not.toBeChecked();
  }

  // --- The tracker, after a real placement.
  await page.getByLabel('Name', { exact: true }).fill('E2E A11y Diner');
  await page.getByLabel('Phone', { exact: true }).fill('716-555-0100');
  await page.getByRole('button', { name: /^Place order/ }).click();
  await expect(page).toHaveURL(/\/order\/track\//);
  await expect(page.getByRole('heading', { name: /^Order #/ })).toBeVisible();
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await expectNoPageOverflow(page, `the tracker at ${viewport.label}`);
  }
  await expectNoAxeViolations(page, 'the order tracker');

  await context.close();
});
