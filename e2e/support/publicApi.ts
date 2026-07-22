/**
 * Reading the public surface from a real browser (M3F, ADR-019).
 *
 * The public menu and public media APIs are host-resolved, so every
 * request here is a top-level navigation in a browser context — see
 * `publicOrigin` in ./namespace for why `page.request` cannot be used.
 * Top-level navigation is not subject to CORS, which is what makes this
 * possible against a backend that deliberately exposes no CORS surface.
 *
 * These are the public *API* — JSON and image bytes. They are not a
 * customer-facing storefront: `apps/storefront` is still the Milestone 1
 * foundation shell, and rendered menu composition is M4 (ADR-019 D1).
 */

import {
  expect,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';

/** The public menu shape this suite asserts against (a partial view). */
export interface PublicMenu {
  business: { slug: string; name: string; currency: string };
  categories: {
    id: string;
    name: string;
    description: string | null;
    items: {
      id: string;
      name: string;
      description: string | null;
      price_minor: number;
      is_available: boolean;
      is_orderable: boolean;
      dietary_tags: string[];
      image: {
        alt_text: string | null;
        width: number;
        height: number;
        url: string;
        variants: {
          variant: string;
          width: number;
          height: number;
          url: string;
        }[];
      } | null;
      modifier_groups: {
        id: string;
        name: string;
        min_select: number;
        max_select: number | null;
        options: { id: string; name: string; price_delta_minor: number }[];
      }[];
    }[];
  }[];
  featured_item_ids: string[];
}

/**
 * A visitor: a fresh context carrying no session cookie and an empty
 * HTTP cache.
 *
 * Both properties are load-bearing. No cookie means a public assertion
 * cannot pass by accident of being signed in. An empty cache matters
 * because successful public media responses are
 * `public, max-age=3600, immutable` (docs/07), so a context that has
 * already fetched an image would answer a later request from its own
 * cache and never ask the server — which would make "this image is no
 * longer served" unprovable.
 */
export async function visitorContext(
  browser: Browser,
): Promise<BrowserContext> {
  return browser.newContext();
}

/** Navigate to `url` and return the HTTP response, never null. */
export async function publicVisit(page: Page, url: string) {
  const response = await page.goto(url);
  if (response === null) {
    throw new Error(`no HTTP response for ${url}`);
  }
  return response;
}

/** The public menu of one tenant host, asserted 200 and parsed. */
export async function readPublicMenu(
  page: Page,
  origin: string,
): Promise<PublicMenu> {
  const response = await publicVisit(page, `${origin}/api/v1/public/menu`);
  expect(response.status()).toBe(200);
  return (await response.json()) as PublicMenu;
}

/**
 * Assert a public URL is the neutral not-found response.
 *
 * The contract is that unknown, foreign, hidden, detached, pending, and
 * malformed all render identically (ADR-013, ADR-017), so this checks the
 * status and that the body discloses nothing beyond the standard
 * envelope — never a storage key, path, or filename.
 */
export async function expectNeutralNotFound(
  page: Page,
  url: string,
): Promise<void> {
  const response = await publicVisit(page, url);
  expect(response.status()).toBe(404);
  const body = await response.text();
  expect(body).not.toMatch(/\.webp|storage|checksum|filename/i);
}
