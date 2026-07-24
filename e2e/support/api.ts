/**
 * Per-test API fixtures (ADR-016 setup boundary): when a spec's
 * prerequisites are not themselves the journey under test, they are
 * created through the real HTTP API — the same origin, Vite proxy, and
 * backend the browser uses. Fixtures authenticate legitimately (login →
 * session → CSRF), attach the exact trusted Origin on unsafe requests,
 * and never bypass authorization, run SQL, or import application code.
 * Invitation tokens pass from issuance response to acceptance request in
 * memory only and are never logged.
 */

import { readFileSync } from 'node:fs';
import { request, type APIRequestContext } from '@playwright/test';
import { ADMIN, ORIGIN, type SpecNamespace } from './namespace';

async function newApiContext(): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: ORIGIN,
    // The backend's fail-closed browser-context CSRF check requires a
    // trusted Origin on unsafe requests; harmless on safe ones.
    extraHTTPHeaders: { Origin: ORIGIN },
  });
}

async function expectOk(
  response: { ok(): boolean; status(): number; text(): Promise<string> },
  what: string,
): Promise<void> {
  if (!response.ok()) {
    throw new Error(
      `fixture: ${what} failed with ${response.status()}: ${await response.text()}`,
    );
  }
}

export interface AdminApi {
  api: APIRequestContext;
  csrf: string;
  dispose: () => Promise<void>;
}

/** Log in as anyone and derive the CSRF token exactly as the UI does. */
async function loginApi(
  email: string,
  password: string,
  who: string,
): Promise<AdminApi> {
  const api = await newApiContext();
  const login = await api.post('/api/v1/auth/login', {
    data: { email, password },
  });
  await expectOk(login, `${who} login`);
  const session = await api.get('/api/v1/auth/session');
  await expectOk(session, `${who} session`);
  const view = (await session.json()) as { csrf_token: string };
  return {
    api,
    csrf: view.csrf_token,
    dispose: async () => {
      await api.dispose();
    },
  };
}

/** Authenticated platform-admin API session with its CSRF token. */
export async function adminApi(): Promise<AdminApi> {
  return loginApi(ADMIN.email, ADMIN.password, 'admin');
}

/** Authenticated session for a namespace's own owner. */
export async function ownerApi(ns: SpecNamespace): Promise<AdminApi> {
  return loginApi(ns.ownerEmail, ns.ownerPassword, `owner ${ns.slug}`);
}

export async function createBusiness(
  admin: AdminApi,
  ns: SpecNamespace,
): Promise<string> {
  const response = await admin.api.post('/api/v1/platform/businesses', {
    data: { name: ns.businessName, slug: ns.slug },
    headers: { 'X-CSRF-Token': admin.csrf },
  });
  await expectOk(response, `create business ${ns.slug}`);
  const body = (await response.json()) as { id: string };
  return body.id;
}

async function inviteOwner(
  admin: AdminApi,
  businessId: string,
  ns: SpecNamespace,
): Promise<string> {
  const response = await admin.api.post(
    `/api/v1/platform/businesses/${businessId}/invitations`,
    {
      data: { email: ns.ownerEmail, role: 'owner' },
      headers: { 'X-CSRF-Token': admin.csrf },
    },
  );
  await expectOk(response, `invite owner for ${ns.slug}`);
  const body = (await response.json()) as { token: string };
  return body.token;
}

async function acceptAsNewUser(
  token: string,
  ns: SpecNamespace,
): Promise<void> {
  // Public acceptance from a fresh anonymous context, exactly as a new
  // user's browser would send it (no session, Origin-validated).
  const anonymous = await newApiContext();
  try {
    const response = await anonymous.post('/api/v1/invitations/accept', {
      data: {
        token,
        display_name: ns.ownerName,
        password: ns.ownerPassword,
      },
    });
    await expectOk(response, `accept invitation for ${ns.slug}`);
  } finally {
    await anonymous.dispose();
  }
}

/**
 * A business with an accepted owner membership, still provisioning.
 * Used where a non-admin actor is the prerequisite, not the journey.
 */
export async function provisionBusinessWithOwner(
  ns: SpecNamespace,
): Promise<{ businessId: string }> {
  const admin = await adminApi();
  try {
    const businessId = await createBusiness(admin, ns);
    const token = await inviteOwner(admin, businessId, ns);
    await acceptAsNewUser(token, ns);
    return { businessId };
  } finally {
    await admin.dispose();
  }
}

/**
 * A visible, photographed menu item, created by the business's own owner.
 *
 * Used where a populated menu is the *prerequisite* rather than the
 * subject — cross-business isolation needs something on the other side of
 * the boundary to fail to reach. Building it through the UI is what
 * `menu.spec.ts` does and is the journey there; here it would only make
 * the boundary test slower. Every call is a real authorized request with
 * the owner's own session and CSRF token; nothing bypasses authorization.
 */
export async function seedPhotographedItem(
  ns: SpecNamespace,
  businessId: string,
  names: { category: string; item: string; altText: string },
): Promise<void> {
  const owner = await ownerApi(ns);
  try {
    const base = `/api/v1/businesses/${businessId}`;
    const headers = { 'X-CSRF-Token': owner.csrf };

    const category = await owner.api.post(`${base}/catalog/categories`, {
      data: { name: names.category },
      headers,
    });
    await expectOk(category, `create category for ${ns.slug}`);
    const categoryId = ((await category.json()) as { id: string }).id;

    const item = await owner.api.post(
      `${base}/catalog/categories/${categoryId}/items`,
      { data: { name: names.item, price_minor: 950 }, headers },
    );
    await expectOk(item, `create item for ${ns.slug}`);
    const itemId = ((await item.json()) as { id: string }).id;

    // The same committed fixture the menu journey uploads through the UI.
    const upload = await owner.api.post(`${base}/media`, {
      multipart: {
        file: {
          name: 'menu-item.png',
          mimeType: 'image/png',
          buffer: readFileSync('fixtures/menu-item.png'),
        },
      },
      headers,
    });
    await expectOk(upload, `upload media for ${ns.slug}`);
    const mediaId = ((await upload.json()) as { id: string }).id;

    // Attaching is what promotes the asset from pending to active, which
    // is what makes it eligible for public delivery at all.
    const attach = await owner.api.post(
      `${base}/catalog/items/${itemId}/image`,
      { data: { media_id: mediaId, alt_text: names.altText }, headers },
    );
    await expectOk(attach, `attach image for ${ns.slug}`);
  } finally {
    await owner.dispose();
  }
}

/** An ACTIVE business with an accepted owner (lifecycle prerequisite). */
export async function provisionActiveBusinessWithOwner(
  ns: SpecNamespace,
): Promise<{ businessId: string }> {
  const admin = await adminApi();
  try {
    const businessId = await createBusiness(admin, ns);
    const token = await inviteOwner(admin, businessId, ns);
    await acceptAsNewUser(token, ns);
    const activate = await admin.api.post(
      `/api/v1/platform/businesses/${businessId}/activate`,
      { data: {}, headers: { 'X-CSRF-Token': admin.csrf } },
    );
    await expectOk(activate, `activate ${ns.slug}`);
    return { businessId };
  } finally {
    await admin.dispose();
  }
}
