import { expect, test, type Page } from '@playwright/test';
import {
  provisionActiveBusinessWithOwner,
  seedPublishedStorefront,
} from '../support/api';
import { expectPageClean, watchPage } from '../support/hygiene';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';
import { signIn } from '../support/ui';

/**
 * The Milestone 5 hours journey (M5E, ADR-025): an owner authors the
 * weekly schedule and a dated exception in the hours workspace (M5C),
 * composes the hours section in the storefront composer (M5D),
 * publishes, and an anonymous visitor on the tenant host sees the
 * schedule, the exception, and the live open/closed status — derived
 * entirely from structured settings, never freeform text.
 *
 * Time-robustness is deliberate and non-negotiable (ADR-025): the server
 * computes `is_open_now` from the real current instant, so overriding
 * the browser clock proves nothing. The open business is open 00:00 to
 * midnight-next-day on every ISO day, so "Open now" holds whenever and
 * wherever the suite runs; the closed business has no schedule at all,
 * so "Closed now" holds the same way. Instant-exact DST assertions stay
 * in the backend unit matrix, where the clock is injected.
 */

const ns = specNamespace('hours');

const HOURS_HEADING = 'Opening hours';
const HOURS_INTRO = 'Kitchen closes 30 minutes before the dining room.';
const EXCEPTION_NOTE = 'Private event — dining room closed';

const DAY_NAMES = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

/**
 * A calendar date ~30 days ahead, as the date input value and the
 * storefront's rendered label. Thirty days sits safely inside both the
 * 550-day write window and the 60-day public display window, with room
 * for any timezone skew between the runner and the tenant zone.
 */
function exceptionDate(): { input: string; label: string } {
  const target = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
  const year = target.getUTCFullYear();
  const month = target.getUTCMonth();
  const day = target.getUTCDate();
  return {
    input: `${String(year)}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
    label: `${MONTH_NAMES[month] ?? ''} ${String(day)}, ${String(year)}`,
  };
}

/** The parsed Restaurant JSON-LD object embedded in the current page. */
async function readJsonLd(page: Page): Promise<Record<string, unknown>> {
  const raw = await page
    .locator('script[type="application/ld+json"]')
    .textContent();
  expect(raw).not.toBeNull();
  return JSON.parse(raw ?? '{}') as Record<string, unknown>;
}

test('an owner authors hours, composes the section, publishes, and a visitor sees the live schedule', async ({
  page,
  browser,
}) => {
  test.setTimeout(600_000);
  const { businessId } = await provisionActiveBusinessWithOwner(ns);
  const exception = exceptionDate();

  await signIn(page, ns.ownerEmail, ns.ownerPassword);

  // --- 1. The weekly schedule, authored in the hours workspace (M5C).
  // Every ISO day opens at midnight and closes at midnight the next day
  // (the D1 next-day choice), so the business is open around the clock
  // and the later public assertion is independent of when this runs.
  await page.goto(`/businesses/${businessId}/hours`);
  await expect(
    page.getByRole('heading', { name: 'Hours', exact: true }),
  ).toBeVisible();
  for (const day of DAY_NAMES) {
    const group = page.getByRole('group', { name: day });
    await group.getByRole('button', { name: `Add hours to ${day}` }).click();
    await group.getByLabel('Opens').fill('00:00');
    await group.getByLabel('Closes', { exact: true }).fill('00:00');
    await group.getByLabel('Closes next day').check();
  }
  await page.getByRole('button', { name: 'Save weekly hours' }).click();
  // The saved schedule reads back through the real GET on reload.
  await page.reload();
  await expect(
    page.getByRole('group', { name: 'Sunday' }).getByLabel('Closes next day'),
  ).toBeChecked();

  // --- 2. A dated closure with a customer-visible note (D6).
  await page.getByRole('button', { name: 'Add exception' }).click();
  const exceptionDialog = page.getByRole('dialog', {
    name: 'Add an exception',
  });
  // Exact: the dialog also contains "Add hours to this date".
  await exceptionDialog
    .getByLabel('Date', { exact: true })
    .fill(exception.input);
  await exceptionDialog.getByLabel('Closed all day').check();
  await exceptionDialog.getByLabel('Note (optional)').fill(EXCEPTION_NOTE);
  await exceptionDialog.getByRole('button', { name: 'Save exception' }).click();
  await expect(exceptionDialog).toHaveCount(0);
  await expect(page.getByText('Closed all day')).toBeVisible();
  await expect(page.getByText(EXCEPTION_NOTE)).toBeVisible();

  // --- 3. The hours section, composed and published (M5D). The dialog
  // offers presentation choices only — no schedule input exists to fill.
  await page.goto(`/businesses/${businessId}/storefront`);
  await page.getByRole('button', { name: 'Add hours section' }).click();
  const sectionDialog = page.getByRole('dialog', {
    name: 'Add hours section',
  });
  await expect(sectionDialog.getByLabel('Opens')).toHaveCount(0);
  await sectionDialog.getByLabel('Heading').fill(HOURS_HEADING);
  await sectionDialog.getByLabel('Introduction (optional)').fill(HOURS_INTRO);
  await sectionDialog.getByRole('button', { name: 'Apply' }).click();
  await expect(sectionDialog).toHaveCount(0);
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(page.getByText('Draft saved.')).toBeVisible();
  await page.getByRole('button', { name: 'Publish…' }).click();
  const publishDialog = page.getByRole('dialog', {
    name: 'Publish this draft?',
  });
  await publishDialog
    .getByRole('button', { name: 'Publish', exact: true })
    .click();
  await expect(page.getByText(/Version 1 —/)).toBeVisible();

  // --- 4. The anonymous visitor under the tenant host.
  const context = await visitorContext(browser);
  try {
    const visitor = await context.newPage();
    const problems = watchPage(visitor);

    const home = await publicVisit(visitor, storefrontOrigin(ns.slug));
    expect(home.status()).toBe(200);
    await expect(
      visitor.getByRole('heading', { name: HOURS_HEADING, level: 2 }),
    ).toBeVisible();
    await expect(visitor.getByText(HOURS_INTRO)).toBeVisible();

    // The live status: open around the clock, so "Open now" regardless
    // of when this runs — computed by the server, never by this test.
    await expect(visitor.getByText('Open now')).toBeVisible();

    // The weekly schedule: all seven days, each open all day.
    for (const day of DAY_NAMES) {
      await expect(visitor.getByText(day, { exact: true })).toBeVisible();
    }
    await expect(visitor.getByText('12:00 AM – 12:00 AM')).toHaveCount(7);

    // The exception, with its date and note as plain text.
    await expect(
      visitor.getByRole('heading', { name: 'Special hours', level: 3 }),
    ).toBeVisible();
    await expect(visitor.getByText(exception.label)).toBeVisible();
    await expect(visitor.getByText(EXCEPTION_NOTE)).toBeVisible();

    // The JSON-LD models the weekly hours (§12.2): one entry per stored
    // interval, through the audited serializer.
    const jsonLd = await readJsonLd(visitor);
    const hours = jsonLd['openingHoursSpecification'] as {
      dayOfWeek: string;
      opens: string;
      closes: string;
    }[];
    expect(hours).toHaveLength(7);
    expect(hours.map((entry) => entry.dayOfWeek)).toEqual(DAY_NAMES);
    for (const entry of hours) {
      expect(entry.opens).toBe('00:00');
      expect(entry.closes).toBe('23:59');
    }

    expectPageClean(problems, 'hours journey visitor');
  } finally {
    await context.close();
  }
});

test('a business with no configured hours is honestly closed on its storefront', async ({
  browser,
}) => {
  test.setTimeout(300_000);
  // Seeded through the API: the prerequisite here is a published hours
  // section over an EMPTY schedule — authoring hours is the journey
  // above, not this test's subject. An empty schedule is a real
  // operational state (M5B): the section renders it honestly rather
  // than hiding, and nothing is fabricated.
  const nsClosed = specNamespace('hours-closed');
  await seedPublishedStorefront(
    nsClosed,
    {
      category: 'Mains',
      item: 'House curry',
      imageAlt: 'A plated curry',
      heroHeading: 'A quiet kitchen',
      heroSubheading: 'Opening soon',
      storyBody: 'The schedule is not posted yet.',
    },
    { hours: 'unscheduled' },
  );

  const context = await visitorContext(browser);
  try {
    const visitor = await context.newPage();
    const problems = watchPage(visitor);

    const home = await publicVisit(visitor, storefrontOrigin(nsClosed.slug));
    expect(home.status()).toBe(200);
    await expect(
      visitor.getByRole('heading', { name: HOURS_HEADING, level: 2 }),
    ).toBeVisible();

    // Closed, with nothing upcoming: only "Closed now" — no fabricated
    // next opening, no special-hours block.
    await expect(visitor.getByText('Closed now')).toBeVisible();
    await expect(visitor.getByText(/opens /)).toHaveCount(0);
    await expect(visitor.getByText('Special hours')).toHaveCount(0);

    // Every day is an honest "Closed" row.
    await expect(visitor.getByText('Closed', { exact: true })).toHaveCount(7);

    // An empty schedule claims nothing in JSON-LD — no key at all.
    const jsonLd = await readJsonLd(visitor);
    expect(jsonLd).not.toHaveProperty('openingHoursSpecification');

    expectPageClean(problems, 'unscheduled hours visitor');
  } finally {
    await context.close();
  }
});
