import { expect, test } from '@playwright/test';
import { provisionActiveBusinessWithOwner } from '../support/api';
import { APEX_ORIGIN, publicOrigin, specNamespace } from '../support/namespace';
import {
  expectNeutralNotFound,
  readPublicMenu,
  visitorContext,
} from '../support/publicApi';

// Spec-owned namespace; the active business is this spec's own API
// fixture — onboarding is not what is under test here.
const ns = specNamespace('pub');

/**
 * Tenant resolution from the request Host, observed from a real browser.
 *
 * The public surface is the one place where the tenant is chosen by the
 * Host and nothing else (ADR-013), and no other spec exercises it. It is
 * verified here before the menu journey depends on it, so a failure in
 * the resolution mechanism can never be mistaken for a failure in menu
 * administration.
 *
 * This is the public *API*. `apps/storefront` remains the Milestone 1
 * foundation shell; a rendered customer-facing menu is M4 (ADR-019 D1).
 */
test('an active business resolves from its own host, and nothing else does', async ({
  browser,
}) => {
  await provisionActiveBusinessWithOwner(ns);

  const visitor = await visitorContext(browser);
  try {
    const page = await visitor.newPage();

    // The tenant host resolves to exactly this business. A brand-new
    // business has no catalog, so an empty menu is the correct answer —
    // and it is a different answer from "not found", which is the point.
    const menu = await readPublicMenu(page, publicOrigin(ns.slug));
    expect(menu.business.slug).toBe(ns.slug);
    expect(menu.business.name).toBe(ns.businessName);
    expect(menu.business.currency).toBe('USD');
    expect(menu.categories).toEqual([]);
    expect(menu.featured_item_ids).toEqual([]);

    // The response carries no administrative or storage vocabulary.
    expect(JSON.stringify(menu)).not.toMatch(
      /position|is_hidden|is_featured|image_media_id|storage|checksum/i,
    );

    // An unknown tenant is the neutral 404 — indistinguishable from a
    // suspended, provisioning, or reserved one by design.
    await expectNeutralNotFound(
      page,
      `${publicOrigin(`${ns.slug}-nonexistent`)}/api/v1/public/menu`,
    );

    // The apex is not a tenant either: `localhost` is zero labels above
    // the base domain, so it resolves to no business at all.
    await expectNeutralNotFound(page, `${APEX_ORIGIN}/api/v1/public/menu`);

    // The public surface is genuinely unauthenticated: this context has
    // never signed in, and the request still succeeded above. Confirm no
    // session cookie was set by any of it.
    const cookies = await visitor.cookies();
    expect(cookies.filter((cookie) => cookie.name === 'session')).toEqual([]);
  } finally {
    await visitor.close();
  }
});

/**
 * The same resolution rule seen from the other side: the control center's
 * own origin can never reach a tenant's public menu, because the dev
 * proxy forwards without rewriting Host. This pins the reason the public
 * assertions in this suite must target the backend origin directly — if
 * the proxy ever gained `changeOrigin: true`, this test would start
 * failing and say why.
 */
test('the control-center origin resolves to no tenant', async ({ page }) => {
  await expectNeutralNotFound(page, '/api/v1/public/menu');
});
