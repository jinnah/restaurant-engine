import { expect, test } from '@playwright/test';
import { provisionBusinessWithOwner } from '../support/api';
import { specNamespace } from '../support/namespace';
import { signIn } from '../support/ui';

// Spec-owned namespace; the non-admin actor is created by this spec's
// own API fixture — never reused from the onboarding journey.
const ns = specNamespace('authz');

/**
 * Negative authorization: the platform area neither renders for nor
 * leaks anything to an authenticated non-administrator. (Server-side
 * 403s are backend-tested; this proves the honest UI surface.)
 */
test('a non-administrator cannot see or reach the platform area', async ({
  page,
}) => {
  await provisionBusinessWithOwner(ns);

  await signIn(page, ns.ownerEmail, ns.ownerPassword);
  // The membership link specifically: the switcher also names the business.
  await expect(page.getByRole('link', { name: ns.businessName })).toBeVisible();
  // No Platform entry is offered at all.
  await expect(
    page.getByRole('link', { name: 'Platform', exact: true }),
  ).toHaveCount(0);

  // A direct deep link renders the standard not-found experience.
  await page.goto('/platform/businesses');
  await expect(
    page.getByRole('heading', { name: 'Page not found' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Platform administration' }),
  ).toHaveCount(0);
  await expect(page.getByText('Create restaurant')).toHaveCount(0);
});
