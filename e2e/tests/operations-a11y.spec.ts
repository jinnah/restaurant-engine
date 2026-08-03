import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { seedOrderingStorefront } from '../support/api';
import { expectNoPageOverflow, expectTargetSize } from '../support/layout';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { visitorContext } from '../support/publicApi';
import { signIn } from '../support/ui';

/**
 * Responsive and accessibility acceptance for the order board (M7D,
 * ADR-027; the blueprint §3.8/§12.4 floors as acceptance criteria, and
 * the §19 criterion "mobile/tablet usability verified"): the board with
 * a live ticket, the open drawer, its in-drawer confirmation, and the
 * pause dialog — scanned at the approved automated rule boundary and
 * held to the 44px target and no-horizontal-scroll floors at a phone and
 * a desktop width.
 *
 * The operator here is the **owner**, because the owner sees the widest
 * board: staff hold no `business.hours.write`, so the pause control and
 * its dialog exist only in this session (ruling D8). Journey 5 covers
 * the staff view of the same surface.
 *
 * It also pins the choices M7C made deliberately, which an automated
 * scan cannot see on its own: filter chips that report their own state
 * inside a named group, an alert region that is mounted before anything
 * arrives, exactly one dialog — and one `dialog-title` — on the page at
 * a time, and a print ticket kept out of the accessibility tree by
 * `display: none` rather than by an `aria-hidden` that would lie about
 * it while it is printing.
 */

const ns = specNamespace('operations-a11y');

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

/** One real pickup order, placed by a visitor in a real browser. */
async function placeOneOrder(page: Page, origin: string): Promise<void> {
  await page.goto(`${origin}/menu`);
  await page.getByRole('button', { name: 'Add to order' }).click();
  const picker = page.getByRole('dialog', { name: CONTENT.item });
  await expect(picker).toBeVisible();
  await picker.getByRole('radio', { name: /Full/ }).check();
  await picker.getByRole('button', { name: /^Add 1/ }).click();
  await page.getByRole('link', { name: 'View order (1)' }).click();
  await page.getByLabel('Name', { exact: true }).fill('E2E Board A11y Diner');
  await page.getByLabel('Phone', { exact: true }).fill('716-555-0100');
  await page.getByRole('button', { name: /^Place order/ }).click();
  await expect(page).toHaveURL(/\/order\/track\//);
}

test('the order board passes the axe boundary and holds the layout floors', async ({
  page,
  browser,
}) => {
  test.setTimeout(600_000);
  const { businessId } = await seedOrderingStorefront(ns, CONTENT);

  // A board with nothing on it proves nothing about a board in service.
  const visitorCtx = await visitorContext(browser);
  try {
    await placeOneOrder(await visitorCtx.newPage(), storefrontOrigin(ns.slug));
  } finally {
    await visitorCtx.close();
  }

  await signIn(page, ns.ownerEmail, ns.ownerPassword);
  await page.goto(`/businesses/${businessId}/orders`);
  await expect(
    page.getByRole('heading', { name: 'Orders', level: 2 }),
  ).toBeVisible();
  const ticket = page.getByRole('button', { name: /#\d/ });
  await expect(ticket).toBeVisible();

  // --- The board, at both widths.
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await expectNoPageOverflow(page, `the board at ${viewport.label}`);
    // The two controls a counter reaches for constantly, measured where
    // the width actually threatens them.
    await expectTargetSize(ticket, `the order ticket at ${viewport.label}`);
    await expectTargetSize(
      page.getByRole('button', { name: 'All active' }),
      `the status filter chip at ${viewport.label}`,
    );
  }
  await expectNoAxeViolations(page, 'the order board');

  // The filters report their own state, inside a group that says what the
  // state is about — the M7C choice a scan cannot infer.
  const filters = page.getByRole('group', { name: 'Filter orders by status' });
  await expect(
    filters.getByRole('button', { name: 'All active' }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(filters.getByRole('button', { name: 'New' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  // The new-order live region is in the ACCESSIBILITY tree before anything
  // arrives — found by role, in a real browser, with the real stylesheet —
  // so an order is an announced update to a region that was already there,
  // not a region appearing (ruling D10). A `display: none` empty region
  // would be absent here and is what M7D corrected.
  await expect(page.getByRole('status')).toHaveCount(1);

  // --- The drawer, open, over the board.
  await ticket.click();
  const drawer = page.getByRole('dialog');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('Pay at pickup')).toBeVisible();
  await expectNoPageOverflow(page, 'the open drawer at desktop');
  await expectNoAxeViolations(page, 'the order board with the drawer open');
  await expectTargetSize(
    drawer.getByRole('button', { name: 'Accept' }),
    'the drawer accept command',
  );
  // The counter must be able to put an order down again without a
  // keyboard: Escape is not a control on a tablet (M7D).
  await expectTargetSize(
    drawer.getByRole('button', { name: 'Close' }),
    'the drawer close control',
  );

  // Exactly one dialog — and exactly one element carrying the shared
  // `dialog-title` id, which is what a nested dialog would have doubled.
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await expect(page.locator('#dialog-title')).toHaveCount(1);

  // The print ticket is in the document, so it can print, and out of the
  // accessibility tree, so it is never announced twice (ruling D12).
  await expect(page.locator('section[aria-label="Print ticket"]')).toHaveCount(
    1,
  );
  await expect(page.getByRole('region', { name: 'Print ticket' })).toHaveCount(
    0,
  );

  await page.setViewportSize({ width: 375, height: 812 });
  await expectNoPageOverflow(page, 'the open drawer at mobile');
  await expectNoAxeViolations(page, 'the drawer at a phone width');

  // --- The in-drawer confirmation: still one dialog, still one title.
  await drawer.getByRole('button', { name: 'Decline' }).click();
  await expect(
    drawer.getByRole('button', { name: /^Decline order #/ }),
  ).toBeFocused();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await expect(page.locator('#dialog-title')).toHaveCount(1);
  await expectNoAxeViolations(page, 'the drawer confirming a refusal');
  // Nothing is refused: the second step is the point, so it is declined.
  await drawer.getByRole('button', { name: 'Keep it' }).click();

  // --- The estimate control, which only exists once work is owed.
  await drawer.getByRole('button', { name: 'Accept' }).click();
  const estimate = drawer.getByRole('group', {
    name: 'Set an estimated ready time',
  });
  await expect(estimate).toBeVisible();
  await expectTargetSize(
    estimate.getByRole('button', { name: '20 min' }),
    'an estimate duration control',
  );
  await expectNoAxeViolations(page, 'the drawer with the estimate control');
  await drawer.getByRole('button', { name: 'Close' }).click();
  await expect(drawer).toHaveCount(0);

  // --- The pause dialog (ruling D8), owner-only and therefore only here.
  await page.getByRole('button', { name: 'Pause ordering…' }).click();
  const pause = page.getByRole('dialog', { name: 'Pause ordering' });
  await expect(pause).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(1);
  await expectNoPageOverflow(page, 'the pause dialog at mobile');
  await expectNoAxeViolations(page, 'the pause dialog');
  // Left as it was found: this business is not paused by an audit.
  await pause.getByRole('button', { name: 'Keep ordering on' }).click();
  await expect(pause).toHaveCount(0);
});
