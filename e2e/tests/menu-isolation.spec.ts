import { expect, test } from '@playwright/test';
import {
  provisionActiveBusinessWithOwner,
  seedPhotographedItem,
} from '../support/api';
import { publicOrigin, specNamespace } from '../support/namespace';
import {
  expectNeutralNotFound,
  readPublicMenu,
  visitorContext,
} from '../support/publicApi';
import { signIn } from '../support/ui';

// This spec owns two namespaces, because a boundary needs two sides
// (ADR-019 D6). Neither is shared with any other spec, and neither is the
// menu journey's — both businesses are built here.
const nsA = specNamespace('menu-a');
const nsB = specNamespace('menu-b');

const A_CATEGORY = 'Curries';
const A_ITEM = 'Shorshe Ilish';
const A_ALT = 'Hilsa in mustard gravy';

/**
 * One business's catalog and media are invisible to another — through the
 * UI and through the host-resolved public surface (blueprint §8.5, §15.3
 * journey 6; the M3 exit criterion's "cross-tenant media and catalog
 * tests").
 *
 * The catalog and image are prerequisites rather than the subject, so they
 * are created through authorized API fixtures using each owner's own
 * session and CSRF token. Building them through the UI is `menu.spec.ts`'s
 * journey; repeating it here would only make the boundary slower to test.
 *
 * The decisive assertion is the media one. A cross-business menu read could
 * plausibly be right by accident of an empty catalog; an image URL is a
 * real, currently-serving resource, and whether it is delivered is decided
 * by the request Host composed with the asset's owning business. Only an
 * end-to-end request under a foreign Host tests that composition.
 */
test('one business cannot see or reach another through the menu or its media', async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);

  const a = await provisionActiveBusinessWithOwner(nsA);
  // B's id is never needed: this test signs in as B's owner and deep-links
  // to A, so the only identifier that has to travel is A's.
  await provisionActiveBusinessWithOwner(nsB);
  await seedPhotographedItem(nsA, a.businessId, {
    category: A_CATEGORY,
    item: A_ITEM,
    altText: A_ALT,
  });

  // --- The public surface separates them ------------------------------
  const visitor = await visitorContext(browser);
  try {
    const visitorPage = await visitor.newPage();

    const menuA = await readPublicMenu(visitorPage, publicOrigin(nsA.slug));
    expect(menuA.business.slug).toBe(nsA.slug);
    expect(menuA.categories.map((category) => category.name)).toEqual([
      A_CATEGORY,
    ]);
    const imageUrl = menuA.categories[0]!.items[0]!.image!.url;

    // Business B resolves to B: its own (empty) menu, and no trace of A.
    const menuB = await readPublicMenu(visitorPage, publicOrigin(nsB.slug));
    expect(menuB.business.slug).toBe(nsB.slug);
    expect(menuB.categories).toEqual([]);
    expect(JSON.stringify(menuB)).not.toContain(A_ITEM);
    expect(JSON.stringify(menuB)).not.toContain(A_CATEGORY);

    // The same image path under B's host is the neutral not-found. The
    // asset id is a real one that is being served right now — one host
    // away — so this is the boundary and not a missing row.
    await expectNeutralNotFound(
      visitorPage,
      `${publicOrigin(nsB.slug)}${imageUrl}`,
    );
    // And it genuinely is served under its own host, so the 404 above
    // cannot be a broken URL.
    const served = await visitorPage.goto(
      `${publicOrigin(nsA.slug)}${imageUrl}`,
    );
    expect(served?.status()).toBe(200);
    expect(served?.headers()['content-type']).toBe('image/webp');
  } finally {
    await visitor.close();
  }

  // --- The control center separates them ------------------------------
  await signIn(page, nsB.ownerEmail, nsB.ownerPassword);

  // The switcher lists memberships, so it lists exactly one business.
  const switcher = page.getByLabel('Switch restaurant', { exact: true });
  await expect(switcher.getByRole('option')).toHaveText([
    '— Choose a restaurant —',
    new RegExp(nsB.businessName),
  ]);
  await expect(page.getByRole('link', { name: nsA.businessName })).toHaveCount(
    0,
  );

  // A deep link into a business B holds no membership in renders the
  // ordinary not-found experience — no hint that it exists.
  await page.goto(`/businesses/${a.businessId}/menu`);
  await expect(
    page.getByRole('heading', { name: 'Page not found' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'New category' })).toHaveCount(
    0,
  );
  await expect(page.getByText(A_CATEGORY)).toHaveCount(0);
  await expect(page.getByText(A_ITEM)).toHaveCount(0);
});
