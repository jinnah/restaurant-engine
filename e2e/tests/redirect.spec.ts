import { expect, test } from '@playwright/test';
import { ADMIN, ORIGIN } from '../support/namespace';

/**
 * Anonymous deep-link round-trip: the guard preserves the intended
 * internal path through login and returns to it — sanitized, same
 * origin, no external target. Needs only the globally seeded admin.
 */
test('an anonymous platform deep link round-trips through login', async ({
  page,
}) => {
  await page.goto('/platform/businesses');
  await expect(page).toHaveURL(/\/login\?next=%2Fplatform%2Fbusinesses/);

  await page.getByLabel('Email').fill(ADMIN.email);
  await page.getByLabel('Password').fill(ADMIN.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();

  await expect(
    page.getByRole('heading', { name: 'Create restaurant' }),
  ).toBeVisible();
  await expect(page).toHaveURL(new RegExp('/platform/businesses$'));
  expect(new URL(page.url()).origin).toBe(ORIGIN);
});
