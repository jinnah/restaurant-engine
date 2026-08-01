import { expect, test, type Page } from '@playwright/test';
import { seedPublishedStorefront, type ThemeSelection } from '../support/api';
import { expectPageClean, watchPage } from '../support/hygiene';
import {
  ADMIN,
  specNamespace,
  storefrontOrigin,
  type SpecNamespace,
} from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';
import { readTenantTokens, type DesignVariantId } from '../support/theme';
import { signIn } from '../support/ui';

/**
 * The platform design-assignment UI, its authorization boundary, and
 * tenant isolation across variants (M4G-D, ADR-024 §2/§11).
 *
 * ADR-024 §2 makes the structural variant platform authority and M4G-C
 * built the first UI for it. This spec proves the governance split works
 * end to end in a browser: a platform administrator assigns through the
 * real UI, the change stays private until the OWNER publishes, and no
 * non-administrator can reach the command at all.
 */

const CATEGORY = 'House specialties';
const ITEM = 'Clay-oven lamb shank';
const IMAGE_ALT = 'The dining room set for dinner service';
const HERO_SUBHEADING = 'A neighborhood kitchen with a wood-fired oven';
const STORY_BODY =
  'The kitchen has been in one family for three generations, and the ' +
  'oven at its center was built by hand before the first table was set.';

const ns = specNamespace('sf-design');
const nsDenied = specNamespace('sf-design-denied');
const nsIsoA = specNamespace('sf-design-iso-a');
const nsIsoB = specNamespace('sf-design-iso-b');

/** The application notification region (role="log"). */
function toasts(page: Page) {
  return page.getByRole('log', { name: 'Notifications' });
}

async function seed(
  namespace: SpecNamespace,
  heading: string,
  design?: {
    variant?: DesignVariantId;
    theme?: ThemeSelection;
    logo?: boolean;
  },
): Promise<{ businessId: string; mediaId: string }> {
  return seedPublishedStorefront(
    namespace,
    {
      category: CATEGORY,
      item: ITEM,
      imageAlt: IMAGE_ALT,
      heroHeading: heading,
      heroSubheading: HERO_SUBHEADING,
      storyBody: STORY_BODY,
    },
    design,
  );
}

test('a platform administrator assigns a design that stays private until the owner publishes it', async ({
  page,
  browser,
}) => {
  test.setTimeout(420_000);

  // A published classic storefront: publication seeds the next draft, so
  // a draft already exists and the assignment below is a real change
  // rather than the first-draft creation path.
  const { businessId } = await seed(ns, 'Wood-fired cooking, all seasons');

  const problems = watchPage(page);

  // --- The platform assigns Editorial through the real UI -------------
  await signIn(page, ADMIN.email, ADMIN.password);
  // Recording starts after sign-in: the unauthenticated session probe
  // answering 401 on the way in is correct bootstrap behaviour and is
  // another spec's subject (see hygiene.clear()).
  problems.clear();
  await page.goto(`/platform/businesses/${businessId}`);
  await expect(
    page.getByRole('heading', { name: 'Design', exact: true }),
  ).toBeVisible();

  // §2/M4G-C: the panel is a command. It shows no current variant and
  // preselects nothing, so the action is unavailable until one is chosen.
  const assign = page.getByRole('button', { name: 'Assign design' });
  await expect(assign).toBeDisabled();

  await page.getByRole('radio', { name: 'Editorial' }).check();
  await expect(assign).toBeEnabled();
  await assign.click();

  const confirm = page.getByRole('dialog', { name: 'Assign this design?' });
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText(
    'The design becomes public only when an owner publishes the draft.',
  );
  await confirm.getByRole('button', { name: 'Assign design' }).click();

  // The acknowledgment reports what the server actually did.
  await expect(page.getByRole('status')).toHaveText(
    'Design changed from Classic to Editorial.',
  );

  // The command's exact no-op is never described as a change.
  await page.getByRole('radio', { name: 'Editorial' }).check();
  await page.getByRole('button', { name: 'Assign design' }).click();
  await page
    .getByRole('dialog', { name: 'Assign this design?' })
    .getByRole('button', { name: 'Assign design' })
    .click();
  await expect(page.getByRole('status')).toHaveText(
    'Editorial was already assigned. No changes were made.',
  );

  // The platform interaction itself is asserted clean here, while its
  // scope is still exactly the platform page.
  expectPageClean(problems, 'platform design assignment');

  // --- The public site is unchanged: assignment is not publication ----
  {
    const context = await visitorContext(browser);
    try {
      const visitor = await context.newPage();
      const home = await publicVisit(visitor, storefrontOrigin(ns.slug));
      expect(home.status()).toBe(200);
      const tokens = await readTenantTokens(visitor);
      expect(
        tokens.variant,
        'the assigned variant must not reach the public site before publication',
      ).toBe('classic');
    } finally {
      await context.close();
    }
  }

  // --- The owner publishes, and only then does the design go public ---
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login/);
  await signIn(page, ns.ownerEmail, ns.ownerPassword);
  problems.clear();
  await page.goto(`/businesses/${businessId}/storefront`);
  await page.getByRole('button', { name: 'Publish…' }).click();
  await page
    .getByRole('dialog', { name: 'Publish this draft?' })
    .getByRole('button', { name: 'Publish', exact: true })
    .click();
  await expect(toasts(page)).toContainText('Storefront published.');

  {
    const context = await visitorContext(browser);
    try {
      const visitor = await context.newPage();
      const visitorProblems = watchPage(visitor);
      const home = await publicVisit(visitor, storefrontOrigin(ns.slug));
      expect(home.status()).toBe(200);
      const tokens = await readTenantTokens(visitor);
      expect(tokens.variant, 'the published variant').toBe('editorial');
      expect(tokens.motion, 'editorial advertises its motion tier').toBe(
        'rich',
      );
      await expect(visitor.locator('h1')).toHaveCount(1);
      expectPageClean(visitorProblems, 'published editorial after assignment');
    } finally {
      await context.close();
    }
  }

  expectPageClean(problems, 'owner publication of the assigned design');
});

test('a non-administrator never reaches the design panel and no assignment is attempted', async ({
  page,
}) => {
  test.setTimeout(300_000);

  const { businessId } = await seed(nsDenied, 'A quiet corner table');

  // Every request the browser makes is recorded, so "the command was
  // never called" is proved rather than inferred from what is on screen.
  const designCalls: string[] = [];
  page.on('request', (request) => {
    if (/\/platform\/businesses\/[^/]+\/design$/.test(request.url())) {
      designCalls.push(`${request.method()} ${request.url()}`);
    }
  });

  await signIn(page, nsDenied.ownerEmail, nsDenied.ownerPassword);
  await page.goto(`/platform/businesses/${businessId}`);

  // ADR-016: an authenticated non-administrator gets the standard
  // not-found experience — presentation only; the backend capability
  // check remains authoritative.
  await expect(
    page.getByRole('heading', { name: 'Page not found' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Design', exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Assign design' })).toHaveCount(
    0,
  );
  expect(designCalls, 'the design command was never called').toEqual([]);
});

test('two tenants assigned different variants each render only their own design', async ({
  browser,
}) => {
  test.setTimeout(420_000);

  await seed(nsIsoA, 'The long table', {
    variant: 'editorial',
    theme: { palette: 'midnight' },
  });
  await seed(nsIsoB, 'Counter service, all day', {
    variant: 'express',
    theme: { palette: 'ember' },
  });

  const context = await visitorContext(browser);
  try {
    const page = await context.newPage();
    const problems = watchPage(page);

    // Tenant A
    expect(
      (await publicVisit(page, storefrontOrigin(nsIsoA.slug))).status(),
    ).toBe(200);
    const a = await readTenantTokens(page);
    expect(a.variant, 'tenant A variant').toBe('editorial');
    await expect(
      page.getByRole('heading', { name: nsIsoA.businessName, level: 1 }),
    ).toBeVisible();
    await expect(page.getByText(nsIsoB.businessName)).toHaveCount(0);

    // Tenant B, same browser context: the host is the only selector.
    expect(
      (await publicVisit(page, storefrontOrigin(nsIsoB.slug))).status(),
    ).toBe(200);
    const b = await readTenantTokens(page);
    expect(b.variant, 'tenant B variant').toBe('express');
    await expect(
      page.getByRole('heading', { name: nsIsoB.businessName, level: 1 }),
    ).toBeVisible();
    await expect(page.getByText(nsIsoA.businessName)).toHaveCount(0);

    // The designs are genuinely distinct, not two names over one layout.
    expect(a.variant, 'the two tenants differ structurally').not.toBe(
      b.variant,
    );
    expect(a.colorBg, 'the two tenants differ in palette').not.toBe(b.colorBg);

    expectPageClean(problems, 'cross-tenant variant isolation');
  } finally {
    await context.close();
  }
});
