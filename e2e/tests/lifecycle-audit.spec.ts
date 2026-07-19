import { expect, test } from '@playwright/test';
import { provisionActiveBusinessWithOwner } from '../support/api';
import { ADMIN, specNamespace } from '../support/namespace';
import { platformNav, signIn } from '../support/ui';

// Spec-owned namespace; the ACTIVE business is this spec's own API
// fixture (activation UX is the onboarding journey's criterion, not
// this test's focus).
const ns = specNamespace('lc');

test('suspension and reactivation are confirmed and visible in the audit trail', async ({
  page,
}) => {
  const { businessId } = await provisionActiveBusinessWithOwner(ns);

  await signIn(page, ADMIN.email, ADMIN.password);
  await page.goto(`/platform/businesses/${businessId}`);
  await expect(page.getByText('active', { exact: true })).toBeVisible();

  // Suspend, through its confirmation dialog.
  await page.getByRole('button', { name: 'Suspend' }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Suspend', exact: true })
    .click();
  await expect(page.getByText('suspended', { exact: true })).toBeVisible();

  // Reactivate, through its confirmation dialog.
  await page.getByRole('button', { name: 'Reactivate' }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Reactivate', exact: true })
    .click();
  await expect(page.getByText('active', { exact: true })).toBeVisible();

  // The audit trail, filtered to exactly this spec's business, shows
  // the lifecycle history. (Cursor load-more is deliberately not
  // asserted: a >page-size fixture would be fabricated bulk data, and
  // fake pagination proves nothing.)
  await platformNav(page).getByRole('link', { name: 'Audit' }).click();
  await page.getByLabel('Business ID').fill(businessId);
  await page.getByRole('button', { name: 'Apply filters' }).click();

  const list = page.getByRole('list', { name: 'Audit events' });
  await expect(list.getByText('business.reactivated')).toBeVisible();
  await expect(list.getByText('business.suspended')).toBeVisible();
  await expect(list.getByText('business.activated')).toBeVisible();
  await expect(list.getByText('business.created')).toBeVisible();
});
