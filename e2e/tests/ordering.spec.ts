import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import {
  deleteItem,
  seedOrderingStorefront,
  setItemAvailability,
} from '../support/api';
import { expectPageClean, watchPage } from '../support/hygiene';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { visitorContext } from '../support/publicApi';

/**
 * The Milestone 6 ordering journeys (M6D, ADR-026; blueprint §15.3
 * journey 4): a visitor customizes an item with modifiers and places one
 * pickup order despite a simulated retry, follows it on the tracker, and
 * the order survives the menu changing under it; a second visitor
 * cancels while the order is still `submitted` (D11); a third finds the
 * menu changed at checkout and the surface fails gracefully (D8/§19).
 *
 * The retry simulation is deliberately a **client-side network failure
 * after submission**: the first placement request is aborted at the
 * transport layer, the surface shows its honest no-duplicate promise,
 * and the second click provably carries the SAME idempotency key — the
 * same command, retried. (Intercept-and-forward double-delivery cannot
 * run here: Playwright's route.fetch executes in Node, and Windows does
 * not resolve `*.localhost` — the recorded ADR-016 constraint. The
 * server-side half of the §19 duplicate proof — a concurrent identical
 * replay returning the one stored order — is the M6A API matrix.)
 *
 * Time-robustness (the ADR-025 doctrine): every business is open around
 * the clock with zero lead time, so ASAP ordering is valid whenever and
 * wherever the suite runs. No spec touches the browser clock.
 */

// Spec-owned namespaces (ADR-019 D6): three, because the cancellation
// and staleness journeys mutate order and menu state the main journey
// must never depend on.
const ns = specNamespace('ordering');
const nsCancel = specNamespace('ordering-cancel');
const nsStale = specNamespace('ordering-stale');

const CONTENT = {
  category: 'Tandoor mains',
  item: 'Clay-oven chicken',
  imageAlt: 'A plated tandoori chicken',
  heroHeading: 'Order tonight from the tandoor',
  heroSubheading: 'Fresh from the clay oven, ready when you are',
  storyBody:
    'Our tandoor was fired for the first time twenty years ago and has ' +
    'not gone cold since.',
};

/** A fresh anonymous visitor page (no cookies, empty cache). */
async function openVisitor(
  browser: Browser,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await visitorContext(browser);
  return { context, page: await context.newPage() };
}

/**
 * Compose the seeded item in the picker: the required single-choice
 * group satisfied with "Full" (+$4.00), one optional "Naan" (+$2.50),
 * quantity 2 — (950 + 400 + 250) × 2 = 3,200 minor units.
 */
async function composeFullOrder(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Add to order' }).click();
  const dialog = page.getByRole('dialog', { name: CONTENT.item });
  await expect(dialog).toBeVisible();
  // The required group blocks confirmation until satisfied.
  await expect(dialog.getByRole('button', { name: /^Add 1/ })).toBeDisabled();
  await dialog.getByRole('radio', { name: /Full/ }).check();
  await dialog.getByRole('checkbox', { name: /Naan/ }).check();
  await dialog.getByRole('button', { name: 'Increase quantity' }).click();
  const confirm = dialog.getByRole('button', { name: /^Add 2/ });
  // The running total is a display hint composed from projection prices.
  await expect(confirm).toContainText('$32.00');
  await confirm.click();
  await expect(dialog).not.toBeVisible();
}

/** Fill the required checkout contact fields. */
async function fillContact(page: Page, name: string): Promise<void> {
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByLabel('Phone', { exact: true }).fill('716-555-0100');
}

test('journey 4: customize with modifiers, order despite a simulated retry, track, and survive menu edits', async ({
  browser,
}) => {
  test.setTimeout(300_000);
  const { businessId, itemId } = await seedOrderingStorefront(ns, CONTENT);
  const origin = storefrontOrigin(ns.slug);
  const { context, page } = await openVisitor(browser);
  const problems = watchPage(page);

  // The gated affordances exist because the D12 gate is on.
  await page.goto(`${origin}/menu`);
  await expect(
    page.getByRole('heading', { level: 2, name: 'Menu' }),
  ).toBeVisible();
  await composeFullOrder(page);
  await page.getByRole('link', { name: 'View order (2)' }).click();

  await expect(page.getByRole('heading', { name: 'Your order' })).toBeVisible();
  await expect(page.getByText('Full, Naan')).toBeVisible();
  await fillContact(page, 'E2E Ordering Diner');
  // The two consents are independent and never pre-checked (D7); one is
  // chosen, one deliberately left unchecked.
  const updates = page.getByRole('checkbox', {
    name: /updates about this order/i,
  });
  const marketing = page.getByRole('checkbox', { name: /news and offers/i });
  await expect(updates).not.toBeChecked();
  await expect(marketing).not.toBeChecked();
  await updates.check();

  // The simulated retry: the first placement dies on the wire after the
  // click; every attempt's payload is captured for the key proof.
  const attempts: string[] = [];
  let failFirst = true;
  await page.route('**/api/v1/public/orders', async (route) => {
    attempts.push(route.request().postData() ?? '');
    if (failFirst) {
      failFirst = false;
      await route.abort('connectionfailed');
      return;
    }
    await route.continue();
  });
  // The aborted request surfaces in the watcher; scope hygiene to what
  // follows the deliberate failure.
  const placeButton = page.getByRole('button', { name: /^Place order/ });
  await expect(placeButton).toContainText('$32.00');
  await placeButton.click();
  await expect(
    page.getByText(/could not be placed .* not .* create a duplicate order/is),
  ).toBeVisible();
  problems.clear();
  await placeButton.click();

  // Confirmation is the tracker, with the snapshot and the promise.
  await expect(page).toHaveURL(/\/order\/track\//);
  await expect(page.getByRole('heading', { name: /^Order #/ })).toBeVisible();
  await expect(page.getByText('Order received')).toBeVisible();
  await expect(page.getByText(`2 × ${CONTENT.item}`)).toBeVisible();
  await expect(page.getByText('Full, Naan')).toBeVisible();
  // Totals are authoritative: the server accepted exactly the displayed
  // expected total, and the tracker renders the stored $32.00 (line and
  // total row alike — the snapshot's own arithmetic).
  await expect(page.getByText('$32.00').first()).toBeVisible();

  // The retry proof: two attempts left the browser, byte-identical in
  // command content — the SAME idempotency key (D2), so the server can
  // only ever have one order for it.
  expect(attempts).toHaveLength(2);
  const first = JSON.parse(attempts[0]!) as Record<string, unknown>;
  const second = JSON.parse(attempts[1]!) as Record<string, unknown>;
  expect(first['idempotency_key']).toBe(second['idempotency_key']);
  expect(second['expected_total_minor']).toBe(3200);

  // The order survives menu edits (§19): the owner deletes the ordered
  // item outright; the snapshot keeps rendering names and prices.
  await deleteItem(ns, businessId, itemId);
  await page.reload();
  await expect(page.getByText(`2 × ${CONTENT.item}`)).toBeVisible();
  await expect(page.getByText('Full, Naan')).toBeVisible();
  await expect(page.getByText('$32.00').first()).toBeVisible();
  await expect(page.getByText('Order received')).toBeVisible();

  expectPageClean(problems, 'the ordering journey');
  await context.close();
});

test('a customer cancels a submitted order from the tracker (D11)', async ({
  browser,
}) => {
  test.setTimeout(300_000);
  await seedOrderingStorefront(nsCancel, CONTENT);
  const origin = storefrontOrigin(nsCancel.slug);
  const { context, page } = await openVisitor(browser);
  const problems = watchPage(page);

  await page.goto(`${origin}/menu`);
  await page.getByRole('button', { name: 'Add to order' }).click();
  const dialog = page.getByRole('dialog', { name: CONTENT.item });
  await dialog.getByRole('radio', { name: /Half/ }).check();
  await dialog.getByRole('button', { name: /^Add 1/ }).click();
  await page.getByRole('link', { name: 'View order (1)' }).click();
  await fillContact(page, 'E2E Cancelling Diner');
  await page.getByRole('button', { name: /^Place order/ }).click();

  await expect(page).toHaveURL(/\/order\/track\//);
  await expect(page.getByText('Order received')).toBeVisible();

  // Two-step, explicit: the first click sends nothing.
  await page.getByRole('button', { name: 'Cancel this order' }).click();
  await expect(
    page.getByRole('button', { name: 'Keep my order' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Yes, cancel it' }).click();
  await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Cancel this order' }),
  ).not.toBeVisible();

  // The cancellation is a stored fact, not page state.
  await page.reload();
  await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Cancel this order' }),
  ).not.toBeVisible();

  expectPageClean(problems, 'the cancellation journey');
  await context.close();
});

test('a stale cart fails gracefully at checkout and recovers (§19)', async ({
  browser,
}) => {
  test.setTimeout(300_000);
  const { businessId, itemId } = await seedOrderingStorefront(nsStale, CONTENT);
  const origin = storefrontOrigin(nsStale.slug);
  const { context, page } = await openVisitor(browser);
  const problems = watchPage(page);

  await page.goto(`${origin}/menu`);
  await page.getByRole('button', { name: 'Add to order' }).click();
  const dialog = page.getByRole('dialog', { name: CONTENT.item });
  await dialog.getByRole('radio', { name: /Half/ }).check();
  await dialog.getByRole('button', { name: /^Add 1/ }).click();
  await page.getByRole('link', { name: 'View order (1)' }).click();
  await expect(page.getByRole('heading', { name: 'Your order' })).toBeVisible();

  // The menu changes while the visitor is at checkout: sold out today.
  await setItemAvailability(nsStale, businessId, itemId, false);

  await fillContact(page, 'E2E Stale-Cart Diner');
  await page.getByRole('button', { name: /^Place order/ }).click();

  // The refusal names the line, honestly, and nothing was placed.
  await expect(
    page.getByText('This item is sold out right now.'),
  ).toBeVisible();
  await expect(
    page.getByText(/the marked lines need attention/i),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/order$/);
  // The 409 above is this journey's subject, not a defect; hygiene
  // scopes to everything after the deliberate refusal (the stated-point
  // pattern the hygiene helper documents).
  problems.clear();

  // Recovery: removing the dead line leaves the honest empty state.
  await page.getByRole('button', { name: `Remove ${CONTENT.item}` }).click();
  await expect(page.getByText(/your order is empty/i)).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Browse the menu' }),
  ).toBeVisible();

  expectPageClean(problems, 'the stale-cart journey');
  await context.close();
});
