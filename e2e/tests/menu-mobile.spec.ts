import { expect, test, type Page } from '@playwright/test';
import { provisionActiveBusinessWithOwner } from '../support/api';
import { specNamespace } from '../support/namespace';
import { signIn } from '../support/ui';

// Spec-owned namespace (ADR-019 D6).
const ns = specNamespace('menu-m');

const CATEGORY = 'Street food';
const ITEM = 'Fuchka';

/**
 * A phone viewport. 375x812 is the width the M3E design work was judged
 * at, so it is the width this keeps honest.
 */
test.use({ viewport: { width: 375, height: 812 } });

/**
 * The document itself must not scroll sideways.
 *
 * A wide *element* may scroll inside its own container — that is a normal
 * responsive pattern — but the page must not, because horizontal document
 * scroll on a phone makes controls drift out of reach. This measures the
 * document, deliberately, rather than hunting for wide descendants.
 */
async function expectNoPageOverflow(page: Page, where: string): Promise<void> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(
    scrollWidth,
    `page scrolls horizontally at ${where} (${String(scrollWidth)} > ${String(clientWidth)})`,
  ).toBeLessThanOrEqual(clientWidth);
}

/**
 * Menu administration on a phone (blueprint §19 M3: "responsive menu
 * administration works on mobile").
 *
 * Until now that criterion rested on a driver assembled per run and never
 * committed, so it could only be re-established by repeating a documented
 * procedure. This makes it a project command: `pnpm e2e` covers it.
 *
 * The core administrative path only — a second project duplicating the
 * whole suite to change one viewport would multiply runtime for very
 * little. What is checked at each screen is what the width actually
 * threatens: the principal control is present and operable, dialogs and
 * forms can be completed rather than merely opened, and the document does
 * not scroll sideways.
 *
 * This is limited engineering evidence about layout and reach at one
 * width. It is not an accessibility audit and no conformance claim is
 * made or implied: no automated accessibility scan is run here, and
 * target size, contrast, and focus order are not assessed.
 */
test('menu administration is usable at a phone width', async ({ page }) => {
  test.setTimeout(120_000);

  await provisionActiveBusinessWithOwner(ns);

  await signIn(page, ns.ownerEmail, ns.ownerPassword);
  await expectNoPageOverflow(page, 'the memberships home');

  // The switcher is a native <select>: at this width the operating system
  // renders its own picker, which is the reason it was chosen.
  await expect(
    page.getByLabel('Switch restaurant', { exact: true }),
  ).toBeVisible();

  await page.getByRole('link', { name: ns.businessName }).click();
  await expect(
    page.getByRole('heading', { name: ns.businessName, level: 1 }),
  ).toBeVisible();
  await expectNoPageOverflow(page, 'the empty workspace menu');

  // A dialog can be completed, not just opened. On the empty menu the primary
  // action is "Add first category" (item 1).
  const newCategory = page.getByRole('button', { name: 'Add first category' });
  await expect(newCategory).toBeEnabled();
  await newCategory.click();
  const dialog = page.getByRole('dialog', { name: 'Add a category' });
  await expect(dialog).toBeVisible();
  await expectNoPageOverflow(page, 'the category dialog');
  await dialog.getByLabel('Name', { exact: true }).fill(CATEGORY);
  await dialog.getByRole('button', { name: 'Add category' }).click();
  await expect(page.getByRole('heading', { name: CATEGORY })).toBeVisible();
  await expectNoPageOverflow(page, 'the menu with one category');

  // A full-page form can be completed. Long, user-supplied names are the
  // realistic overflow risk on a narrow row, so the item is saved and the
  // overview re-measured with it present.
  await page.getByRole('link', { name: `Add item to ${CATEGORY}` }).click();
  await expectNoPageOverflow(page, 'the new-item form');
  await page.getByLabel('Name', { exact: true }).fill(ITEM);
  await page.getByLabel('Price (USD)', { exact: true }).fill('4.25');
  await page.getByRole('button', { name: 'Add item' }).click();
  await expect(page).toHaveURL(/\/menu\/items\/[0-9a-f-]{36}$/);
  await expectNoPageOverflow(page, 'the item editor');

  // The editor's principal controls are reachable at this width.
  await expect(
    page.getByRole('button', { name: 'Add a photo', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'New group' })).toBeVisible();

  // The image picker is the densest dialog in the workspace: a grid, a
  // file input, and a description field inside a modal.
  await page.getByRole('button', { name: 'Add a photo', exact: true }).click();
  const picker = page.getByRole('dialog', { name: 'Choose an image' });
  await expect(picker).toBeVisible();
  await expect(
    picker.getByLabel('Upload a new image', { exact: true }),
  ).toBeVisible();
  await expectNoPageOverflow(page, 'the image picker');
  await picker.getByRole('button', { name: 'Cancel' }).click();

  await page.getByRole('link', { name: 'Back to the menu' }).click();
  // Exact: the row also carries a "Manage <item>" action (item 6), which a
  // loose name match would select alongside the item-name link.
  await expect(
    page.getByRole('link', { name: ITEM, exact: true }),
  ).toBeVisible();
  // The Manage action (item 6) is reachable at this width, not just the name.
  await expect(
    page.getByRole('link', { name: `Manage ${ITEM}` }),
  ).toBeVisible();
  await expectNoPageOverflow(page, 'the menu with one item');
});
