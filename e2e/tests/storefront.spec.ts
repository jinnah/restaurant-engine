import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import {
  ownerApi,
  provisionActiveBusinessWithOwner,
  seedPhotographedItem,
} from '../support/api';
import { ADMIN, specNamespace, storefrontOrigin } from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';
import { signIn } from '../support/ui';

// This spec owns two namespaces (ADR-019 D6): the storefront journey's
// business, and a second active-but-never-published business proving the
// rendered surface separates hosts. Neither is any other spec's.
const ns = specNamespace('sf');
const nsB = specNamespace('sf-b');

const CATEGORY = 'Mains';
const ITEM = 'Riverside lamb curry';
const ITEM_ALT = 'Lamb curry in a copper pot';

// Version 1 content, composed through the UI. Distinctive strings are the
// point: "this text is/is not on the public host" must be unambiguous.
const V1_HEADING = 'Wood-fired classics since 1988';
const V1_SUBHEADING = 'Family recipes, cooked over an open flame';
const MENU_HEADING = 'From our kitchen';
const MENU_INTRO = 'Cooked to order, every single plate.';
const STORY_HEADING = 'Our story';
const STORY_BODY =
  'Three generations of one family have run this kitchen. The tandoor was ' +
  'built by hand, and the recipes have never been written down.';
const CONTACT_HEADING = 'Visit us';
const ADDRESS_LINE = '12 Riverside Avenue';
const PHONE = '(716) 555-0142';
const GALLERY_HEADING = 'The dining room';
const HERO_ALT = 'The dining room set for dinner service';
const GALLERY_ALT = 'Fresh naan straight from the tandoor';

// Version 2 changes exactly the hero heading, so published-versus-draft
// and archived-versus-current stay distinguishable by one string.
const V2_HEADING = 'A new season, a new menu';

/** The application notification region (role="log"). */
function toasts(page: Page) {
  return page.getByRole('log', { name: 'Notifications' });
}

/** A fresh anonymous visitor page (no cookies, empty cache). */
async function openVisitor(
  browser: Browser,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await visitorContext(browser);
  return { context, page: await context.newPage() };
}

/**
 * Select the seeded library image in the media picker and describe it.
 * The picker replaces the section dialog while open; confirming returns
 * to the section dialog with the reference staged (claimed at save).
 */
async function pickLibraryImage(page: Page, altText: string): Promise<void> {
  const picker = page.getByRole('dialog', { name: 'Choose an image' });
  await expect(picker).toBeVisible();
  await picker.getByRole('button', { name: /^menu-item\.png/ }).click();
  await picker
    .getByRole('radio', { name: 'Describe this image', exact: true })
    .check();
  await picker.getByLabel('Description', { exact: true }).fill(altText);
  await picker.getByRole('button', { name: 'Use this image' }).click();
}

/** Publish the saved draft through its confirmation dialog. */
async function publishDraft(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Publish…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Publish this draft?' });
  await dialog.getByRole('button', { name: 'Publish', exact: true }).click();
  await expect(toasts(page)).toContainText('Storefront published.');
}

/**
 * The complete storefront journey (M4F, ADR-023): mandatory journeys 2
 * and 3 become complete for the first time — compose, save, preview,
 * publish, render publicly under the tenant host, keep the draft private,
 * archive, restore, republish, and survive suspension — all through the
 * rendered UI and documented HTTP, never an internal seam.
 */
test('an owner composes, publishes, restores, and the public host renders only published versions', async ({
  page,
  browser,
}) => {
  test.setTimeout(420_000);

  // Prerequisites through established API fixtures: two active
  // businesses and a photographed menu item for the journey's tenant.
  // Menu building is journey 2's already-covered half (menu.spec.ts);
  // storefront composition is THIS journey and happens through the UI.
  const { businessId } = await provisionActiveBusinessWithOwner(ns);
  await provisionActiveBusinessWithOwner(nsB);
  const { itemId } = await seedPhotographedItem(ns, businessId, {
    category: CATEGORY,
    item: ITEM,
    altText: ITEM_ALT,
  });
  // Featured status drives the menu section's home-page composition; it
  // is catalog prerequisite state, not this journey's subject.
  {
    const owner = await ownerApi(ns);
    try {
      const featured = await owner.api.patch(
        `/api/v1/businesses/${businessId}/catalog/items/${itemId}`,
        {
          data: { is_featured: true },
          headers: { 'X-CSRF-Token': owner.csrf },
        },
      );
      expect(featured.ok()).toBe(true);
    } finally {
      await owner.dispose();
    }
  }

  // --- 1. The owner reaches the storefront workspace ------------------
  await signIn(page, ns.ownerEmail, ns.ownerPassword);
  await page.getByRole('link', { name: ns.businessName }).click();
  await page
    .getByRole('navigation', { name: 'Workspace sections' })
    .getByRole('link', { name: 'Storefront' })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Storefront', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('No draft yet')).toBeVisible();
  await expect(page.getByText('Never published')).toBeVisible();

  // --- 2. A draft with all five section types, through the dialogs ----
  await page.getByRole('button', { name: 'Add hero section' }).click();
  const heroDialog = page.getByRole('dialog', { name: 'Add hero section' });
  await heroDialog.getByLabel('Heading', { exact: true }).fill(V1_HEADING);
  await heroDialog
    .getByLabel('Supporting line (optional)', { exact: true })
    .fill(V1_SUBHEADING);
  await heroDialog
    .getByLabel('Button', { exact: true })
    .selectOption('view_menu');
  await heroDialog.getByRole('button', { name: 'Choose a photo' }).click();
  await pickLibraryImage(page, HERO_ALT);
  await heroDialog.getByRole('button', { name: 'Apply' }).click();

  await page.getByRole('button', { name: 'Add menu section' }).click();
  const menuDialog = page.getByRole('dialog', { name: 'Add menu section' });
  await menuDialog.getByLabel('Heading', { exact: true }).fill(MENU_HEADING);
  await menuDialog
    .getByLabel('Introduction (optional)', { exact: true })
    .fill(MENU_INTRO);
  await menuDialog.getByRole('button', { name: 'Apply' }).click();

  await page.getByRole('button', { name: 'Add story section' }).click();
  const storyDialog = page.getByRole('dialog', { name: 'Add story section' });
  await storyDialog.getByLabel('Heading', { exact: true }).fill(STORY_HEADING);
  await storyDialog.getByLabel('Story', { exact: true }).fill(STORY_BODY);
  await storyDialog.getByRole('button', { name: 'Apply' }).click();

  await page.getByRole('button', { name: 'Add contact section' }).click();
  const contactDialog = page.getByRole('dialog', {
    name: 'Add contact section',
  });
  await contactDialog
    .getByLabel('Heading', { exact: true })
    .fill(CONTACT_HEADING);
  await contactDialog.getByRole('button', { name: 'Add address line' }).click();
  await contactDialog.getByLabel('Line 1', { exact: true }).fill(ADDRESS_LINE);
  await contactDialog
    .getByLabel('Phone (optional)', { exact: true })
    .fill(PHONE);
  await contactDialog.getByRole('button', { name: 'Apply' }).click();

  await page.getByRole('button', { name: 'Add gallery section' }).click();
  const galleryDialog = page.getByRole('dialog', {
    name: 'Add gallery section',
  });
  await galleryDialog
    .getByLabel('Heading (optional)', { exact: true })
    .fill(GALLERY_HEADING);
  await galleryDialog.getByRole('button', { name: 'Add photo' }).click();
  await pickLibraryImage(page, GALLERY_ALT);
  await galleryDialog.getByRole('button', { name: 'Apply' }).click();

  // --- 3. Explicit save (create intent; media claimed here) -----------
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(toasts(page)).toContainText('Draft saved.');

  // --- 5. The unpublished draft is not on the public host --------------
  {
    const { context, page: visitor } = await openVisitor(browser);
    try {
      const response = await publicVisit(visitor, storefrontOrigin(ns.slug));
      expect(response.status()).toBe(404);
      await expect(
        visitor.getByRole('heading', { name: 'Page not found' }),
      ).toBeVisible();
      await expect(visitor.getByText(V1_HEADING)).toHaveCount(0);
      await expect(visitor.getByText(ns.businessName)).toHaveCount(0);
    } finally {
      await context.close();
    }
  }

  // --- 4. The saved-draft preview renders through the shared renderer --
  await page.getByRole('link', { name: 'Preview', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Storefront preview' }),
  ).toBeVisible();
  await expect(page.getByText(V1_HEADING)).toBeVisible();
  await expect(page.getByText(V1_SUBHEADING)).toBeVisible();
  // Preview navigation is structurally inert (ADR-022 §3): the same
  // anchor, no href, no link role announced.
  const previewCta = page.getByText('View menu', { exact: true });
  await expect(previewCta).toBeVisible();
  await expect(previewCta).not.toHaveAttribute('href', /./);
  await page.getByRole('link', { name: 'Back to storefront' }).click();

  // --- 6. Version 1 is published ---------------------------------------
  await publishDraft(page);
  await expect(page.getByText(/Version 1 —/)).toBeVisible();

  // --- 7/8/9. The public tenant host renders version 1 -----------------
  {
    const { context, page: visitor } = await openVisitor(browser);
    try {
      const response = await publicVisit(visitor, storefrontOrigin(ns.slug));
      expect(response.status()).toBe(200);

      // Tenant identity and chrome: h1 is the business name (ADR-021).
      await expect(
        visitor.getByRole('heading', { name: ns.businessName, level: 1 }),
      ).toBeVisible();

      // Every section, in composition order (h2 order is section order).
      const sectionHeadings = visitor.getByRole('heading', { level: 2 });
      await expect(sectionHeadings).toHaveText([
        V1_HEADING,
        MENU_HEADING,
        STORY_HEADING,
        CONTACT_HEADING,
        GALLERY_HEADING,
      ]);
      await expect(visitor.getByText(V1_SUBHEADING)).toBeVisible();
      await expect(visitor.getByText(MENU_INTRO)).toBeVisible();
      await expect(visitor.getByText(STORY_BODY)).toBeVisible();
      await expect(visitor.getByText(ADDRESS_LINE)).toBeVisible();
      await expect(visitor.getByText(PHONE)).toBeVisible();

      // The hero call to action is a real link on the public host.
      await expect(
        visitor.getByRole('link', { name: 'View menu', exact: true }),
      ).toHaveAttribute('href', '/menu');

      // Claimed media is genuinely delivered on the tenant origin: the
      // hero image's bytes arrived (naturalWidth is 0 for a broken img).
      const heroImage = visitor.getByRole('img', { name: HERO_ALT });
      await expect(heroImage).toBeVisible();
      await expect
        .poll(async () =>
          heroImage.evaluate(
            (element) => (element as HTMLImageElement).naturalWidth,
          ),
        )
        .toBeGreaterThan(0);
      await expect(
        visitor.getByRole('img', { name: GALLERY_ALT }),
      ).toBeVisible();

      // The featured item composed from the live public menu.
      await expect(visitor.getByText(ITEM).first()).toBeVisible();

      // --- 8. The public /menu route -----------------------------------
      await visitor
        .getByRole('link', { name: 'View menu', exact: true })
        .click();
      await expect(
        visitor.getByRole('heading', { name: 'Menu', level: 2 }),
      ).toBeVisible();
      await expect(
        visitor.getByRole('heading', { name: CATEGORY, level: 3 }),
      ).toBeVisible();
      await expect(visitor.getByText(ITEM).first()).toBeVisible();
      await expect(visitor.getByText('$9.50').first()).toBeVisible();
      await expect(visitor.getByRole('img', { name: ITEM_ALT })).toBeVisible();

      // --- 10. Cross-host isolation on the rendered surface ------------
      // Business B is active but has never published: its host renders
      // the neutral 404 and carries nothing of A's content.
      const bResponse = await publicVisit(visitor, storefrontOrigin(nsB.slug));
      expect(bResponse.status()).toBe(404);
      await expect(visitor.getByText(V1_HEADING)).toHaveCount(0);
      await expect(visitor.getByText(ns.businessName)).toHaveCount(0);
    } finally {
      await context.close();
    }
  }

  // --- 11. The draft becomes version 2 (edit + save) --------------------
  await page.getByRole('button', { name: 'Edit Hero' }).click();
  const editHero = page.getByRole('dialog', { name: 'Hero section' });
  await editHero.getByLabel('Heading', { exact: true }).fill(V2_HEADING);
  await editHero.getByRole('button', { name: 'Apply' }).click();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect(toasts(page)).toContainText('Draft saved.');

  // The changed draft is NOT public: the host still renders version 1.
  {
    const { context, page: visitor } = await openVisitor(browser);
    try {
      await publicVisit(visitor, storefrontOrigin(ns.slug));
      await expect(visitor.getByText(V1_HEADING)).toBeVisible();
      await expect(visitor.getByText(V2_HEADING)).toHaveCount(0);
    } finally {
      await context.close();
    }
  }

  // --- 12/13/14. Version 2 publishes; version 1 archives ----------------
  await publishDraft(page);
  await expect(page.getByText(/Version 2 —/)).toBeVisible();

  {
    const { context, page: visitor } = await openVisitor(browser);
    try {
      await publicVisit(visitor, storefrontOrigin(ns.slug));
      await expect(visitor.getByText(V2_HEADING)).toBeVisible();
      await expect(visitor.getByText(V1_HEADING)).toHaveCount(0);
    } finally {
      await context.close();
    }
  }

  // --- 15. Archived version 1 remains historical state ------------------
  await page.getByRole('link', { name: 'History', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Storefront history' }),
  ).toBeVisible();
  const historyRows = page.getByRole('listitem');
  await expect(historyRows.filter({ hasText: 'Version 2' })).toContainText(
    'Published',
  );
  await expect(historyRows.filter({ hasText: 'Version 1' })).toContainText(
    'Archived',
  );

  // --- 16/17. Restore archived version 1 into the draft -----------------
  await page.getByRole('link', { name: 'Version 1', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Version 1 (archived)' }),
  ).toBeVisible();
  await expect(page.getByText(V1_HEADING)).toBeVisible();
  await page
    .getByRole('button', { name: 'Restore this version to the draft' })
    .click();
  const restoreDialog = page.getByRole('dialog', {
    name: 'Restore version 1?',
  });
  await restoreDialog
    .getByRole('button', { name: 'Restore to draft', exact: true })
    .click();
  await expect(toasts(page)).toContainText('Version 1 restored to your draft.');
  await expect(
    page.getByText('This draft was restored from version 1.'),
  ).toBeVisible();

  // Restoration did not publish: the public host still renders v2.
  {
    const { context, page: visitor } = await openVisitor(browser);
    try {
      await publicVisit(visitor, storefrontOrigin(ns.slug));
      await expect(visitor.getByText(V2_HEADING)).toBeVisible();
      await expect(visitor.getByText(V1_HEADING)).toHaveCount(0);
    } finally {
      await context.close();
    }
  }

  // --- 18/19. Publishing the restored draft brings version 1 back -------
  await publishDraft(page);
  await expect(page.getByText(/Version 3 —/)).toBeVisible();

  {
    const { context, page: visitor } = await openVisitor(browser);
    try {
      await publicVisit(visitor, storefrontOrigin(ns.slug));
      await expect(visitor.getByText(V1_HEADING)).toBeVisible();
      await expect(visitor.getByText(V1_SUBHEADING)).toBeVisible();
      await expect(visitor.getByText(V2_HEADING)).toHaveCount(0);
    } finally {
      await context.close();
    }
  }

  // --- 20/21. Suspension hides the published site; reactivation restores
  // exactly the same published output. The platform actions run in their
  // own authenticated context, never the owner's.
  const adminContext = await browser.newContext();
  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN.email, ADMIN.password);
    await adminPage.goto(`/platform/businesses/${businessId}`);
    await adminPage.getByRole('button', { name: 'Suspend' }).click();
    await adminPage
      .getByRole('dialog')
      .getByRole('button', { name: 'Suspend', exact: true })
      .click();
    await expect(
      adminPage.getByText('suspended', { exact: true }),
    ).toBeVisible();

    {
      const { context, page: visitor } = await openVisitor(browser);
      try {
        const response = await publicVisit(visitor, storefrontOrigin(ns.slug));
        expect(response.status()).toBe(404);
        await expect(visitor.getByText(V1_HEADING)).toHaveCount(0);
        await expect(visitor.getByText(ns.businessName)).toHaveCount(0);
      } finally {
        await context.close();
      }
    }

    await adminPage.getByRole('button', { name: 'Reactivate' }).click();
    await adminPage
      .getByRole('dialog')
      .getByRole('button', { name: 'Reactivate', exact: true })
      .click();
    await expect(adminPage.getByText('active', { exact: true })).toBeVisible();

    {
      const { context, page: visitor } = await openVisitor(browser);
      try {
        const response = await publicVisit(visitor, storefrontOrigin(ns.slug));
        expect(response.status()).toBe(200);
        await expect(visitor.getByText(V1_HEADING)).toBeVisible();
        await expect(visitor.getByText(V2_HEADING)).toHaveCount(0);
      } finally {
        await context.close();
      }
    }
  } finally {
    await adminContext.close();
  }
});
