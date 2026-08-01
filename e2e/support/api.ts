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
import type { DesignVariantId, PaletteId, TypePairingId } from './theme';

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
): Promise<{ itemId: string; mediaId: string }> {
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
    return { itemId, mediaId };
  } finally {
    await owner.dispose();
  }
}

/**
 * The platform design-assignment command (M4G-D, ADR-024 §2).
 *
 * The structural variant is platform authority — the M4B command is its
 * only write path and owners never submit one — so a spec that needs a
 * non-default variant must go through a real platform-administrator
 * session exactly as the Control Center does. Assigning when no draft
 * exists creates the first draft from the platform defaults (ADR-020
 * §5.7), which is why callers read the draft's lock version afterwards
 * instead of assuming create-intent.
 */
export async function assignDesign(
  businessId: string,
  variant: DesignVariantId,
): Promise<{
  design_variant: DesignVariantId;
  previous_variant: DesignVariantId | null;
}> {
  const admin = await adminApi();
  try {
    const response = await admin.api.put(
      `/api/v1/platform/businesses/${businessId}/design`,
      {
        data: { design_variant: variant },
        headers: { 'X-CSRF-Token': admin.csrf },
      },
    );
    await expectOk(response, `assign the ${variant} design to ${businessId}`);
    return (await response.json()) as {
      design_variant: DesignVariantId;
      previous_variant: DesignVariantId | null;
    };
  } finally {
    await admin.dispose();
  }
}

/**
 * Upload the committed fixture image as a fresh **pending** asset and
 * return its id (M4G-D).
 *
 * A theme logo is staged, not attached: nothing promotes it, and the
 * draft save is what claims it (ADR-020 §10, widened by ADR-024 §7). A
 * separate upload rather than the catalog item's asset keeps the claim
 * genuinely distinct, and reusing the one committed PNG adds no binary
 * to the repository.
 */
export async function uploadPendingMedia(
  ns: SpecNamespace,
  businessId: string,
): Promise<string> {
  const owner = await ownerApi(ns);
  try {
    const upload = await owner.api.post(
      `/api/v1/businesses/${businessId}/media`,
      {
        multipart: {
          file: {
            name: 'menu-item.png',
            mimeType: 'image/png',
            buffer: readFileSync('fixtures/menu-item.png'),
          },
        },
        headers: { 'X-CSRF-Token': owner.csrf },
      },
    );
    await expectOk(upload, `upload pending media for ${ns.slug}`);
    return ((await upload.json()) as { id: string }).id;
  } finally {
    await owner.dispose();
  }
}

/**
 * The curated theme selections a spec may make (ADR-024 §3).
 *
 * Every field is optional and omitted keys are simply absent from the
 * submitted document, so the backend's registered defaults apply — which
 * is what keeps the pre-M4G fixture shape byte-identical for the M4F
 * specs that pass no selection at all.
 */
export interface ThemeSelection {
  accent?: string;
  palette?: PaletteId;
  typePairing?: TypePairingId;
  logoMediaId?: string;
}

/**
 * The storefront composition seeded for the responsive and accessibility
 * specs (M4F, ADR-023): all five registered section types, realistic
 * tenant copy, and the library image referenced from the hero and the
 * gallery. Content is a *prerequisite* for those specs — composing it
 * through the UI is the functional journey's subject, not theirs — so it
 * travels the documented administrative HTTP contract with the owner's
 * own session and CSRF token, exactly like the menu fixtures above.
 *
 * M4G-D adds the optional curated theme selections. They are spread in
 * only when supplied, so an existing caller submits exactly the document
 * it submitted before.
 */
export function storefrontConfigFixture(
  content: {
    heroHeading: string;
    heroSubheading: string;
    storyBody: string;
    mediaId: string;
    imageAlt: string;
  } & ThemeSelection,
): Record<string, unknown> {
  return {
    schema_version: 1,
    theme: {
      accent: content.accent ?? '#7a1f2b',
      ...(content.palette === undefined ? {} : { palette: content.palette }),
      ...(content.typePairing === undefined
        ? {}
        : { type_pairing: content.typePairing }),
      ...(content.logoMediaId === undefined
        ? {}
        : { logo: { media_id: content.logoMediaId } }),
    },
    sections: [
      {
        id: 'hero',
        type: 'hero',
        enabled: true,
        props: {
          heading: content.heroHeading,
          subheading: content.heroSubheading,
          image: { media_id: content.mediaId, alt_text: content.imageAlt },
          primary_action: 'view_menu',
        },
      },
      {
        id: 'menu',
        type: 'menu',
        enabled: true,
        props: {
          heading: 'From our kitchen',
          intro:
            'Every dish is cooked to order with ingredients we would serve our own family.',
        },
      },
      {
        id: 'story',
        type: 'story',
        enabled: true,
        props: { heading: 'Our story', body: content.storyBody },
      },
      {
        id: 'contact',
        type: 'contact',
        enabled: true,
        props: {
          heading: 'Visit us',
          address_lines: ['12 Riverside Avenue', 'Buffalo, NY 14201'],
          phone: '(716) 555-0142',
          email: 'hello@example-restaurant.example',
        },
      },
      {
        id: 'gallery',
        type: 'gallery',
        enabled: true,
        props: {
          heading: 'The dining room',
          images: [{ media_id: content.mediaId, alt_text: content.imageAlt }],
        },
      },
    ],
  };
}

/**
 * An ACTIVE business with a populated menu, a featured photographed item,
 * and a PUBLISHED five-section storefront. Draft save claims the media
 * reference (ADR-020 §10); publication is what makes anything public.
 *
 * M4G-D adds the optional `design` argument. Supplying a `variant` runs
 * the real platform command first, which creates the draft — so the save
 * then presents that draft's exact lock version instead of claiming
 * create-intent. Omitting `design` entirely leaves the original
 * create-intent path exactly as the M4F specs exercise it.
 */
export async function seedPublishedStorefront(
  ns: SpecNamespace,
  content: {
    category: string;
    item: string;
    imageAlt: string;
    heroHeading: string;
    heroSubheading: string;
    storyBody: string;
  },
  design?: {
    variant?: DesignVariantId;
    theme?: ThemeSelection;
    logo?: boolean;
  },
): Promise<{ businessId: string; mediaId: string; logoMediaId?: string }> {
  const { businessId } = await provisionActiveBusinessWithOwner(ns);
  const { itemId, mediaId } = await seedPhotographedItem(ns, businessId, {
    category: content.category,
    item: content.item,
    altText: content.imageAlt,
  });

  if (design?.variant !== undefined) {
    await assignDesign(businessId, design.variant);
  }
  const logoMediaId =
    design?.logo === true
      ? await uploadPendingMedia(ns, businessId)
      : undefined;

  const owner = await ownerApi(ns);
  try {
    const base = `/api/v1/businesses/${businessId}`;
    const headers = { 'X-CSRF-Token': owner.csrf };

    // Featured items are the menu section's home-page composition.
    const feature = await owner.api.patch(`${base}/catalog/items/${itemId}`, {
      data: { is_featured: true },
      headers,
    });
    await expectOk(feature, `feature item for ${ns.slug}`);

    // Intent is read, never guessed (ADR-020 §5.4): the overview is the
    // only administrative draft read, and a design assignment above has
    // already created the row this save must claim to know about.
    const overview = await owner.api.get(`${base}/storefront`);
    await expectOk(overview, `read storefront overview for ${ns.slug}`);
    const existing = (
      (await overview.json()) as { draft: { lock_version: number } | null }
    ).draft;

    const draft = await owner.api.put(`${base}/storefront/draft`, {
      data: {
        config: storefrontConfigFixture({
          heroHeading: content.heroHeading,
          heroSubheading: content.heroSubheading,
          storyBody: content.storyBody,
          mediaId,
          imageAlt: content.imageAlt,
          ...design?.theme,
          ...(logoMediaId === undefined ? {} : { logoMediaId }),
        }),
        ...(existing === null
          ? {}
          : { expected_lock_version: existing.lock_version }),
      },
      headers,
    });
    await expectOk(draft, `save storefront draft for ${ns.slug}`);
    const draftBody = (await draft.json()) as { lock_version: number };

    const publish = await owner.api.post(`${base}/storefront/publish`, {
      data: { expected_lock_version: draftBody.lock_version },
      headers,
    });
    await expectOk(publish, `publish storefront for ${ns.slug}`);
    return {
      businessId,
      mediaId,
      ...(logoMediaId === undefined ? {} : { logoMediaId }),
    };
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
