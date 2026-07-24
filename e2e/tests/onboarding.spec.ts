import { expect, test } from '@playwright/test';
import { ADMIN, specNamespace } from '../support/namespace';
import { platformNav, signIn, signOut } from '../support/ui';

// Spec-owned namespace: nothing here is shared with any other spec.
const ns = specNamespace('onb');

/**
 * The mandatory onboarding journey (blueprint §15.3 #1), one cohesive
 * test because its steps form one business journey: create → honest
 * missing-owner conflict → invite → one-time token → guest acceptance →
 * owner sees the membership → activation. Every step runs through the
 * real UI; the only precondition is the globally seeded administrator.
 */
test('a platform administrator onboards a business and owner end to end', async ({
  page,
}) => {
  // Sign in and reach the platform area through its navigation.
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByRole('link', { name: 'Platform', exact: true }).click();
  await platformNav(page).getByRole('link', { name: 'Businesses' }).click();

  // Create the spec-owned business.
  await page.getByLabel('Name').fill(ns.businessName);
  await page.getByLabel('Slug').fill(ns.slug);
  await page.getByRole('button', { name: 'Create restaurant' }).click();
  await expect(page.getByText('Restaurant created')).toBeVisible();

  // Open its detail page from the refreshed list.
  await page.getByRole('link', { name: new RegExp(ns.businessName) }).click();
  await expect(
    page.getByRole('heading', { name: new RegExp(ns.businessName) }),
  ).toBeVisible();

  // Activation before any owner exists: the server's honest conflict.
  await page.getByRole('button', { name: 'Activate', exact: true }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Activate', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText(/owner/i);

  // Issue the owner invitation; the token exists ONLY in the reveal UI.
  await page.getByLabel('Email', { exact: true }).fill(ns.ownerEmail);
  await page.getByLabel('Role').selectOption('owner');
  await page.getByRole('button', { name: 'Issue invitation' }).click();
  await expect(page.getByText(/shown once/i)).toBeVisible();
  const token = (await page.getByTestId('one-time-token').innerText()).trim();
  expect(token.length).toBeGreaterThan(20);

  // Token hygiene: never in the URL or persistent storage.
  expect(page.url()).not.toContain(token);
  const storedState = await page.evaluate(() =>
    JSON.stringify([
      Object.entries(window.localStorage),
      Object.entries(window.sessionStorage),
    ]),
  );
  expect(storedState).not.toContain(token);

  // Hand over: sign out and accept as a brand-new user (public UI).
  await signOut(page);
  await page.goto('/invitations/accept');
  await page.getByLabel('Invitation token').fill(token);
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByText(ns.businessName)).toBeVisible(); // preview
  await page.getByLabel('Your name').fill(ns.ownerName);
  await page.getByLabel('Password', { exact: true }).fill(ns.ownerPassword);
  await page.getByLabel('Confirm password').fill(ns.ownerPassword);
  await page.getByRole('button', { name: 'Accept invitation' }).click();
  await expect(
    page.getByRole('heading', { name: 'Invitation accepted' }),
  ).toBeVisible();
  // Acceptance did not sign the visitor in, and the URL stayed clean.
  expect(page.url()).not.toContain(token);

  // The new owner signs in and sees the (still provisioning) membership.
  await page.getByRole('link', { name: 'Go to sign in' }).click();
  await page.getByLabel('Email').fill(ns.ownerEmail);
  await page.getByLabel('Password').fill(ns.ownerPassword);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  // The owner lands on their Restaurant Dashboard (item 1).
  await expect(
    page.getByRole('heading', { name: 'Restaurant Dashboard' }),
  ).toBeVisible();
  // Role-scoped rather than a bare text match: the business name now also
  // appears in the workspace switcher's <option>, so a loose getByText would
  // resolve to two elements.
  await expect(page.getByRole('link', { name: ns.businessName })).toBeVisible();
  await expect(page.getByText('provisioning', { exact: true })).toBeVisible();

  // Back to the administrator: activation now succeeds.
  await signOut(page);
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByRole('link', { name: 'Platform', exact: true }).click();
  await platformNav(page).getByRole('link', { name: 'Businesses' }).click();
  await page.getByRole('link', { name: new RegExp(ns.businessName) }).click();
  await page.getByRole('button', { name: 'Activate', exact: true }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Activate', exact: true })
    .click();
  await expect(page.getByText('active', { exact: true })).toBeVisible();
});
