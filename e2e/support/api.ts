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

/** Authenticated platform-admin API session with its CSRF token. */
export async function adminApi(): Promise<AdminApi> {
  const api = await newApiContext();
  const login = await api.post('/api/v1/auth/login', {
    data: { email: ADMIN.email, password: ADMIN.password },
  });
  await expectOk(login, 'admin login');
  const session = await api.get('/api/v1/auth/session');
  await expectOk(session, 'admin session');
  const view = (await session.json()) as { csrf_token: string };
  return {
    api,
    csrf: view.csrf_token,
    dispose: async () => {
      await api.dispose();
    },
  };
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
