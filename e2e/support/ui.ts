import { expect, type Page } from '@playwright/test';

/** Sign in through the real login UI and land on the memberships home. */
export async function signIn(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Control center' }),
  ).toBeVisible();
}

export async function signOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login/);
}

/** The platform sub-navigation (scoped to avoid overview-card links). */
export function platformNav(page: Page) {
  return page.getByRole('navigation', { name: 'Platform sections' });
}
