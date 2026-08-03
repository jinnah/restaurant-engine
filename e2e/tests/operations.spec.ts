import { expect, test } from '@playwright/test';
import { seedOrderingStorefront, seedTeamMember } from '../support/api';
import { expectPageClean, watchPage } from '../support/hygiene';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { visitorContext } from '../support/publicApi';
import { signIn } from '../support/ui';

/**
 * The Milestone 7 operations journey (M7D, ADR-027; blueprint §15.3
 * journey 5): **staff** accept, prepare, and mark an order ready on the
 * board, and the visitor watching `/order/track/{token}` sees each
 * transition — plus the kitchen's own estimate (ruling D7) — arrive by
 * itself.
 *
 * Two things are deliberate about how that is proven.
 *
 * The operator is a real `staff` membership, invited by the business's
 * own owner, not the owner in a staff-shaped costume. Ruling D2 grants
 * `business.orders.operate` to owner, manager, AND staff, and this is
 * the only place that claim is exercised through a browser: the same
 * session that runs the board is shown holding no storefront section at
 * all (ADR-020 §7), so the capability boundary is visible in the chrome.
 *
 * The visitor's page is **never reloaded**. The tracker polls at 15 s
 * (M6C) and the §19 criterion is that it *reflects* transitions, so each
 * assertion simply waits for the poll it already does — a reload would
 * prove the read endpoint and nothing about the customer's live page.
 * Playwright launches Chromium with background-timer throttling
 * disabled, so the interval keeps running while the staff tab is the one
 * being driven; the timeout below leaves room for several cycles anyway.
 */

// Spec-owned namespace (ADR-019 D6). The staff member's names are
// derived from the same key, so they belong to this spec exactly as the
// namespace does and can collide with nothing else in the suite.
const ns = specNamespace('operations');

const STAFF = {
  email: 'staff-operations@e2e.example',
  displayName: 'E2E Operations Staff',
  // Synthetic, E2E-only; lives only in the disposable e2e database.
  password: 'e2e-only staff pw operations 9152!',
  role: 'staff',
} as const;

const DINER = 'E2E Operations Diner';

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

/** One poll of the tracker's 15 s interval, with generous headroom. */
const POLL_WAIT = { timeout: 45_000 };

test('journey 5: staff accept, prepare, and mark ready while the visitor watches', async ({
  page,
  browser,
}) => {
  test.setTimeout(600_000);
  const { businessId } = await seedOrderingStorefront(ns, CONTENT);
  await seedTeamMember(ns, businessId, STAFF);

  // --- 1. The customer half: one real pickup order, placed in a browser.
  const context = await visitorContext(browser);
  const visitor = await context.newPage();
  const visitorProblems = watchPage(visitor);
  const staffProblems = watchPage(page);

  await visitor.goto(`${storefrontOrigin(ns.slug)}/menu`);
  await visitor.getByRole('button', { name: 'Add to order' }).click();
  const picker = visitor.getByRole('dialog', { name: CONTENT.item });
  await expect(picker).toBeVisible();
  await picker.getByRole('radio', { name: /Full/ }).check();
  await picker.getByRole('button', { name: /^Add 1/ }).click();
  await visitor.getByRole('link', { name: 'View order (1)' }).click();
  await visitor.getByLabel('Name', { exact: true }).fill(DINER);
  await visitor.getByLabel('Phone', { exact: true }).fill('716-555-0100');
  await visitor.getByRole('button', { name: /^Place order/ }).click();

  await expect(visitor).toHaveURL(/\/order\/track\//);
  const trackerHeading = visitor.getByRole('heading', { name: /^Order #/ });
  await expect(trackerHeading).toBeVisible();
  await expect(visitor.getByText('Order received')).toBeVisible();

  // The number the counter will call out: the one handle the customer's
  // page and the restaurant's board share.
  const headingText = ((await trackerHeading.textContent()) ?? '').trim();
  const orderNumber = /^Order #(\d+)$/.exec(headingText)?.[1];
  if (orderNumber === undefined) {
    throw new Error(`unexpected tracker heading: "${headingText}"`);
  }

  // --- 2. The staff half: a genuine staff session, in the workspace.
  await signIn(page, STAFF.email, STAFF.password);
  // The Control Center's unauthenticated bootstrap probes the session and
  // is answered 401 before anyone has signed in; that is another spec's
  // subject, so hygiene is scoped to the authenticated use that follows
  // (the stated-point pattern the hygiene helper documents).
  staffProblems.clear();

  await page.getByRole('link', { name: ns.businessName }).click();
  const nav = page.getByRole('navigation', { name: 'Workspace sections' });
  await expect(nav.getByRole('link', { name: 'Orders' })).toBeVisible();
  // The other half of ruling D2's boundary: staff hold no storefront
  // capability at all, so no storefront section is offered to the very
  // session that is about to advance an order.
  await expect(nav.getByRole('link', { name: 'Storefront' })).toHaveCount(0);
  await nav.getByRole('link', { name: 'Orders' }).click();

  await expect(
    page.getByRole('heading', { name: 'Orders', level: 2 }),
  ).toBeVisible();
  // The board's default view is every active order, undated (M7C).
  const ticket = page.getByRole('button', {
    name: new RegExp(`#${orderNumber}\\b`),
  });
  await expect(ticket).toBeVisible();
  await expect(ticket).toContainText(DINER);
  // Operational language on the chip, never the wire value.
  await expect(ticket).toContainText('New');

  await ticket.click();
  const drawer = page.getByRole('dialog', { name: `Order #${orderNumber}` });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText(DINER, { exact: true })).toBeVisible();
  // Exact: the same line is also on the (display:none) print ticket, with
  // its chosen option appended.
  await expect(
    drawer.getByText(`1 × ${CONTENT.item}`, { exact: true }),
  ).toBeVisible();
  // Exactly the legal commands for `submitted` (D1/D4) — and no others.
  await expect(drawer.getByRole('button', { name: 'Accept' })).toBeVisible();
  await expect(drawer.getByRole('button', { name: 'Decline' })).toBeVisible();
  await expect(
    drawer.getByRole('button', { name: 'Start preparing' }),
  ).toHaveCount(0);
  await expect(drawer.getByRole('button', { name: 'Mark ready' })).toHaveCount(
    0,
  );

  // --- 3. Accept. The customer's page finds out on its own.
  await drawer.getByRole('button', { name: 'Accept' }).click();
  await expect(drawer.getByText('Accepted', { exact: true })).toBeVisible();
  await expect(
    visitor.getByText('Accepted by the restaurant'),
    'the tracker did not reflect the acceptance',
  ).toBeVisible(POLL_WAIT);

  // The kitchen's estimate (D7) is a duration here and an instant there.
  await drawer.getByRole('button', { name: '20 min' }).click();
  await expect(
    visitor.getByText(/^Estimated ready:/),
    'the tracker did not reflect the kitchen estimate',
  ).toBeVisible(POLL_WAIT);

  // --- 4. Prepare.
  await drawer.getByRole('button', { name: 'Start preparing' }).click();
  await expect(drawer.getByText('Preparing', { exact: true })).toBeVisible();
  await expect(
    visitor.getByText('Being prepared'),
    'the tracker did not reflect the start of preparation',
  ).toBeVisible(POLL_WAIT);

  // --- 5. Ready.
  await drawer.getByRole('button', { name: 'Mark ready' }).click();
  await expect(drawer.getByText('Ready', { exact: true })).toBeVisible();
  await expect(
    visitor.getByText('Ready for pickup'),
    'the tracker did not reflect the order being ready',
  ).toBeVisible(POLL_WAIT);

  // The append-only trail (D6): the customer's placement, then one member
  // event per staff action — the actor arm ADR-026 left unwritten.
  await expect(drawer.getByText(/^New — /)).toBeVisible();
  for (const status of ['Accepted', 'Preparing', 'Ready']) {
    await expect(
      drawer.getByText(new RegExp(`^${status} — .+ \\(staff\\)$`)),
      `no member timeline entry for ${status}`,
    ).toBeVisible();
  }

  // A ready order owes only pickup, so `complete` is all that is offered.
  await expect(drawer.getByRole('button', { name: 'Complete' })).toBeVisible();
  await expect(drawer.getByRole('button', { name: 'Mark ready' })).toHaveCount(
    0,
  );

  // Back on the board, the ticket carries the same truth.
  await drawer.getByRole('button', { name: 'Close' }).click();
  await expect(drawer).toHaveCount(0);
  await expect(ticket).toContainText('Ready');

  expectPageClean(visitorProblems, 'the journey 5 visitor');
  expectPageClean(staffProblems, 'the journey 5 staff board');
  await context.close();
});
