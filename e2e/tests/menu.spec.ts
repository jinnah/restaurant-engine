import { expect, test, type Page } from '@playwright/test';
import { provisionActiveBusinessWithOwner } from '../support/api';
import { publicOrigin, specNamespace } from '../support/namespace';
import {
  expectNeutralNotFound,
  publicVisit,
  readPublicMenu,
  visitorContext,
} from '../support/publicApi';
import { signIn } from '../support/ui';

// Spec-owned namespace; the active business is this spec's own API
// fixture. Onboarding and activation are the onboarding journey's
// subject, not this one's — but the business must be ACTIVE, because a
// business only resolves publicly once it is.
const ns = specNamespace('menu');

const CATEGORY = 'Biryani';
const FEATURED_ITEM = 'Chicken Biryani';
const HIDDEN_ITEM = 'Beef Biryani';
const GROUP = 'Choose a side';
const CHOICE = 'Raita';
const ALT_TEXT = 'Chicken biryani on a steel plate';
/** The library names each entry by its sanitized original filename. */
const FIXTURE_NAME = 'menu-item.png';
/**
 * The library tile itself.
 *
 * Anchored at the start for two reasons: an unattached upload is `pending`,
 * so the tile legitimately appends "Not used yet — expires …" and an exact
 * match would miss it; and the entry's delete control is named
 * "Delete menu-item.png", which an unanchored match would also select.
 */
const FIXTURE_TILE = /^menu-item\.png/;

/** The application notification region (role="log", never role="status"). */
function toasts(page: Page) {
  return page.getByRole('log', { name: 'Notifications' });
}

/**
 * Every label lookup here is exact.
 *
 * `getByLabel` is a substring match, and a notification stays on screen
 * for six seconds carrying an accessible name built from its own message
 * — `Dismiss: Category “Biryani” added.` As written loosely, the item
 * form's `Category` select and that dismiss button are two matches for
 * one locator, and the failure arrives a step later than the cause. Exact
 * matching removes the whole class.
 */
function field(page: Page, label: string) {
  return page.getByLabel(label, { exact: true });
}

/** Open the workspace menu page for the item with this name. */
async function openItem(page: Page, name: string): Promise<void> {
  await page.getByRole('link', { name, exact: true }).click();
  await expect(page.getByRole('heading', { name, level: 2 })).toBeVisible();
}

/**
 * The Milestone 3 vertical slice: an owner builds a menu in the control
 * center, and it becomes visible on the tenant's public surface.
 *
 * One cohesive test because the steps form one business narrative, in the
 * shape the onboarding journey established. It is deliberately the
 * *smallest* menu that can prove the milestone — one category, two items,
 * one option group, one choice, one image — because every extra entity
 * costs runtime and adds failure surface without adding evidence. Rules
 * that the backend and component suites already pin (limit conflicts,
 * price and quota ceilings, ETag semantics, name normalization) are not
 * re-proved here.
 *
 * The public surface is the host-resolved public **API**: JSON and image
 * bytes. `apps/storefront` is still the Milestone 1 foundation shell, so
 * a rendered customer-facing menu is not part of this and belongs to M4
 * (ADR-019 D1).
 */
test('an owner builds a menu and it becomes publicly visible', async ({
  page,
  browser,
}) => {
  // A vertical slice is legitimately longer than a single-screen journey:
  // it provisions a business, drives a dozen screens, uploads an image
  // the server decodes and re-encodes into three renditions, and reads
  // the public surface from two further browser contexts. The default
  // 30 s is a sensible ceiling for the other specs and is left alone.
  test.setTimeout(180_000);

  const { businessId } = await provisionActiveBusinessWithOwner(ns);

  // --- The workspace -------------------------------------------------
  await signIn(page, ns.ownerEmail, ns.ownerPassword);
  await page.getByRole('link', { name: ns.businessName }).click();
  await expect(
    page.getByRole('heading', { name: ns.businessName, level: 1 }),
  ).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/businesses/${businessId}/menu$`));
  await expect(page.getByText('Your menu is empty')).toBeVisible();

  // --- A category ----------------------------------------------------
  await page.getByRole('button', { name: 'Add category' }).click();
  const categoryDialog = page.getByRole('dialog', { name: 'Add a category' });
  await categoryDialog.getByLabel('Name', { exact: true }).fill(CATEGORY);
  await categoryDialog.getByRole('button', { name: 'Add category' }).click();
  await expect(toasts(page)).toContainText(new RegExp(`${CATEGORY}.+added`));
  await expect(page.getByRole('heading', { name: CATEGORY })).toBeVisible();

  // --- The featured item ---------------------------------------------
  // 12.50 is the money proof: it must arrive as exactly 1250 minor units
  // on the public API, which a floating-point conversion would not
  // guarantee.
  await page.getByRole('link', { name: `Add item to ${CATEGORY}` }).click();
  await field(page, 'Name').fill(FEATURED_ITEM);
  await field(page, 'Price (USD)').fill('12.50');
  await expect(field(page, 'Category')).toHaveValue(/.+/); // preselected
  await page.getByRole('button', { name: 'Add item' }).click();
  await expect(page).toHaveURL(/\/menu\/items\/[0-9a-f-]{36}$/);

  // Dietary attributes and featuring are edit-mode controls: a new item
  // starts visible, available and unfeatured by contract.
  await field(page, 'Halal').check();
  await field(page, 'Feature this item').check();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(toasts(page)).toContainText(
    new RegExp(`${FEATURED_ITEM}.+saved`),
  );

  // --- Its photo ------------------------------------------------------
  await page.getByRole('button', { name: 'Add a photo', exact: true }).click();
  const picker = page.getByRole('dialog', { name: 'Choose an image' });
  await picker
    .getByLabel('Upload a new image', { exact: true })
    .setInputFiles(`fixtures/${FIXTURE_NAME}`);
  // The library tile appearing is what proves the upload finished; the
  // dialog stays dismissable throughout, so nothing here waits on a
  // spinner. A generous bound covers image decode and re-encode.
  const uploaded = picker.getByRole('button', { name: FIXTURE_TILE });
  await expect(uploaded).toBeVisible({ timeout: 30_000 });
  // Uploaded but not yet attached: the asset is `pending`, and the library
  // says so rather than hiding it (ADR-017 R7).
  await expect(uploaded).toContainText('Not used yet');
  await picker
    .getByRole('radio', { name: 'Describe this image', exact: true })
    .check();
  await picker.getByLabel('Description', { exact: true }).fill(ALT_TEXT);
  await picker.getByRole('button', { name: 'Use for this item' }).click();
  await expect(toasts(page)).toContainText('Photo saved for this item.');
  await expect(page.getByRole('img', { name: ALT_TEXT })).toBeVisible();

  // --- One required option group with one choice ----------------------
  await page.getByRole('button', { name: 'New group' }).click();
  const groupDialog = page.getByRole('dialog', { name: 'Add an option group' });
  await groupDialog.getByLabel('Group name', { exact: true }).fill(GROUP);
  await groupDialog
    .getByLabel('The customer must choose from this group', { exact: true })
    .check();
  await groupDialog.getByRole('button', { name: 'Add group' }).click();
  // With no choices yet the group is honestly reported as unselectable,
  // and the save still succeeded — satisfiability advises, never blocks
  // (ADR-017 D5).
  await expect(page.getByText('Not currently selectable.')).toBeVisible();

  await page.getByRole('button', { name: `Add a choice to ${GROUP}` }).click();
  const choiceDialog = page.getByRole('dialog', { name: 'Add a choice' });
  await choiceDialog.getByLabel('Choice name', { exact: true }).fill(CHOICE);
  await choiceDialog
    .getByLabel('Extra charge (USD)', { exact: true })
    .fill('1.00');
  await choiceDialog.getByRole('button', { name: 'Add choice' }).click();
  await expect(page.getByText('Not currently selectable.')).toHaveCount(0);
  await expect(page.getByText('1 available choice')).toBeVisible();

  // --- A second, hidden item ------------------------------------------
  await page.getByRole('link', { name: 'Back to the menu' }).click();
  await page.getByRole('link', { name: `Add item to ${CATEGORY}` }).click();
  await field(page, 'Name').fill(HIDDEN_ITEM);
  await field(page, 'Price (USD)').fill('14.00');
  await page.getByRole('button', { name: 'Add item' }).click();
  await field(page, 'Hide from the public menu').check();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(toasts(page)).toContainText(new RegExp(`${HIDDEN_ITEM}.+saved`));

  // --- The overview reflects both -------------------------------------
  await page.getByRole('link', { name: 'Back to the menu' }).click();
  await expect(page.getByText(`Featured items: 1`)).toContainText(
    FEATURED_ITEM,
  );
  await expect(page.getByText('2 items')).toBeVisible();

  // --- The reorder controls persist the requested order ---------------
  // Buttons and an explicit position field are the whole mechanism —
  // there is no drag-and-drop anywhere (ADR-018 ruling 5). This asserts
  // that the requested order is saved and rendered, not how it was
  // driven.
  await page
    .getByRole('button', { name: `Arrange items in ${CATEGORY}` })
    .click();
  await page.getByRole('button', { name: `Move ${HIDDEN_ITEM} up` }).click();
  await page.getByRole('button', { name: 'Save item order' }).click();
  await expect(toasts(page)).toContainText(`Item order saved for ${CATEGORY}.`);
  await expect(
    page.getByRole('link', {
      name: new RegExp(`${FEATURED_ITEM}|${HIDDEN_ITEM}`),
    }),
  ).toHaveText([HIDDEN_ITEM, FEATURED_ITEM]);

  // --- The public surface ---------------------------------------------
  const visitor = await visitorContext(browser);
  const visitorPage = await visitor.newPage();
  const origin = publicOrigin(ns.slug);

  const menu = await readPublicMenu(visitorPage, origin);
  expect(menu.business.slug).toBe(ns.slug);
  expect(menu.business.currency).toBe('USD');
  expect(menu.categories).toHaveLength(1);

  const category = menu.categories[0]!;
  expect(category.name).toBe(CATEGORY);
  // The hidden item is absent entirely — not present-and-flagged.
  expect(category.items.map((item) => item.name)).toEqual([FEATURED_ITEM]);

  const item = category.items[0]!;
  expect(item.price_minor).toBe(1250); // 12.50, exactly
  expect(item.dietary_tags).toEqual(['halal']);
  expect(item.is_available).toBe(true);
  expect(item.is_orderable).toBe(true);
  expect(menu.featured_item_ids).toEqual([item.id]);

  expect(item.modifier_groups).toHaveLength(1);
  const group = item.modifier_groups[0]!;
  expect(group.name).toBe(GROUP);
  expect(group.min_select).toBe(1);
  expect(group.max_select).toBeNull();
  expect(group.options).toHaveLength(1);
  expect(group.options[0]!.name).toBe(CHOICE);
  expect(group.options[0]!.price_delta_minor).toBe(100); // 1.00, exactly

  // The image is described by URL and true pixel dimensions, and carries
  // no asset id, storage key, or filename.
  const image = item.image!;
  expect(image.alt_text).toBe(ALT_TEXT);
  expect(image.width).toBe(800);
  expect(image.height).toBe(600);
  expect(image.url).toMatch(
    /^\/api\/v1\/public\/media\/[0-9a-f-]{36}\/canonical$/,
  );
  // 800 px canonical, so the strictly-narrower widths exist and 1280 does
  // not (ADR-017 R3/R4).
  expect(image.variants.map((variant) => variant.variant).sort()).toEqual([
    'w320',
    'w640',
  ]);

  // --- The bytes are really served -------------------------------------
  const canonicalUrl = `${origin}${image.url}`;
  const canonical = await publicVisit(visitorPage, canonicalUrl);
  expect(canonical.status()).toBe(200);
  expect(canonical.headers()['content-type']).toBe('image/webp');
  expect(canonical.headers()['etag']).toBeTruthy();
  expect((await canonical.body()).byteLength).toBeGreaterThan(0);

  const w320 = image.variants.find((variant) => variant.variant === 'w320')!;
  const variantResponse = await publicVisit(
    visitorPage,
    `${origin}${w320.url}`,
  );
  expect(variantResponse.status()).toBe(200);
  expect(variantResponse.headers()['content-type']).toBe('image/webp');
  expect(w320.width).toBe(320);

  // --- Sold out is a listing state, not a visibility state -------------
  // One control, one status word (item 7): marking sold out reveals the
  // single "Sold out" status; marking available removes it.
  await openItem(page, FEATURED_ITEM);
  await page.getByRole('button', { name: 'Mark sold out' }).click();
  await expect(page.getByText('Sold out', { exact: true })).toBeVisible();

  const soldOutMenu = await readPublicMenu(visitorPage, origin);
  const soldOutItem = soldOutMenu.categories[0]!.items[0]!;
  expect(soldOutItem.name).toBe(FEATURED_ITEM); // still listed
  expect(soldOutItem.is_available).toBe(false);
  expect(soldOutItem.is_orderable).toBe(false);

  await page.getByRole('button', { name: 'Mark available' }).click();
  await expect(
    page.getByRole('button', { name: 'Mark sold out' }),
  ).toBeVisible();
  await expect(page.getByText('Sold out', { exact: true })).toHaveCount(0);

  // --- Detaching and deleting are different operations ------------------
  // Deleting an image a menu item still points at is refused: the RESTRICT
  // foreign key surfaces as a 409 rather than orphaning the row. The
  // library is where deletion lives, so that is where the refusal is read.
  await page.getByRole('button', { name: 'Replace photo' }).click();
  const library = page.getByRole('dialog', { name: 'Choose an image' });
  await library.getByRole('button', { name: `Delete ${FIXTURE_NAME}` }).click();
  await library.getByRole('button', { name: 'Delete permanently' }).click();
  await expect(library.getByRole('alert')).toContainText(
    'This image is still used by a menu item.',
  );
  // Refused, so it is still there — and still offered, because detaching
  // makes the very same action legal.
  await expect(
    library.getByRole('button', { name: `Delete ${FIXTURE_NAME}` }),
  ).toBeVisible();
  await library.getByRole('button', { name: 'Cancel' }).click();

  // Detach, then delete the now-unreferenced asset from the library. This
  // is the sequence the milestone's own guidance describes, and until the
  // M3F correction the asset became unreachable at exactly this point.
  await page.getByRole('button', { name: 'Remove from item' }).click();
  await expect(toasts(page)).toContainText('Photo removed from this item.');

  await page.getByRole('button', { name: 'Add a photo', exact: true }).click();
  await library.getByRole('button', { name: `Delete ${FIXTURE_NAME}` }).click();
  await library.getByRole('button', { name: 'Delete permanently' }).click();
  // Gone from the rendered library, not merely from a local list.
  await expect(library.getByText('You have no images yet')).toBeVisible();
  await expect(
    library.getByRole('button', { name: `Delete ${FIXTURE_NAME}` }),
  ).toHaveCount(0);
  await library.getByRole('button', { name: 'Cancel' }).click();

  // The public menu drops the image, and the bytes stop being served.
  const finalMenu = await readPublicMenu(visitorPage, origin);
  expect(finalMenu.categories[0]!.items[0]!.image).toBeNull();

  // A context that already fetched this URL would answer from its own
  // cache — public media is `max-age=3600, immutable` — so the takedown
  // is checked from a visitor that has never seen it.
  const secondVisitor = await visitorContext(browser);
  try {
    await expectNeutralNotFound(await secondVisitor.newPage(), canonicalUrl);
  } finally {
    await secondVisitor.close();
  }

  await visitor.close();
});
