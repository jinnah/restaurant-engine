// Injected fake for the generated facade (ADR-009): tests exercise the
// real routes and components with a typed, per-test scripted client.

import { vi } from 'vitest';
import type {
  AdminMenu,
  ApiClient,
  ApiResult,
  BusinessSummary,
  CategoryWithItems,
  ErrorEnvelope,
  ItemSummary,
  MembershipSummary,
  SessionView,
} from '@restaurant-engine/api-client';

export const INVALID_INVITATION = 'Invitation is not valid or has expired.';
export const INVALID_RESET = 'Reset token is not valid or has expired.';

export function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

export function apiError(
  status: number | null,
  envelope: ErrorEnvelope | null = null,
): ApiResult<never> {
  return { ok: false, status, envelope };
}

export function envelope(
  code: string,
  message: string,
  fieldErrors: { field: string; code: string; message: string }[] = [],
): ErrorEnvelope {
  return {
    error: {
      code,
      message,
      correlation_id: null,
      field_errors: fieldErrors,
    },
  } as ErrorEnvelope;
}

export function membership(
  overrides: Partial<MembershipSummary> = {},
): MembershipSummary {
  return {
    business_id: '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001',
    business_slug: 'shalik',
    business_name: 'Shalik',
    role: 'owner',
    business_status: 'active',
    ...overrides,
  };
}

export function sessionView(overrides: Partial<SessionView> = {}): SessionView {
  return {
    user: {
      id: '2f6b8d4e-1a3c-4f5b-8e9d-0c1a2b3c4d5e',
      email: 'owner@example.com',
      display_name: 'Test Owner',
      is_platform_admin: false,
    },
    csrf_token: 'csrf-token-1',
    memberships: [membership()],
    ...overrides,
  };
}

/** An authenticated platform administrator with no memberships. */
export function adminSessionView(
  overrides: Partial<SessionView> = {},
): SessionView {
  return sessionView({
    user: {
      id: '9c1e5b7a-3d2f-4a6b-8c0d-1e2f3a4b5c6d',
      email: 'admin@example.com',
      display_name: 'Platform Admin',
      is_platform_admin: true,
    },
    memberships: [],
    ...overrides,
  });
}

export function business(
  overrides: Partial<BusinessSummary> = {},
): BusinessSummary {
  return {
    id: '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001',
    name: 'Shalik',
    slug: 'shalik',
    status: 'provisioning',
    currency: 'USD',
    timezone: 'America/New_York',
    created_at: '2026-07-19T00:00:00Z',
    updated_at: '2026-07-19T00:00:00Z',
    ...overrides,
  };
}

export interface ClientOverrides {
  auth?: Partial<ApiClient['auth']>;
  invitations?: Partial<ApiClient['invitations']>;
  passwordResets?: Partial<ApiClient['passwordResets']>;
  platform?: Partial<ApiClient['platform']>;
  businesses?: Partial<ApiClient['businesses']>;
  catalog?: Partial<ApiClient['catalog']>;
  media?: Partial<ApiClient['media']>;
}

/** An empty administrative menu — the starting point for most menu tests. */
export function adminMenu(categories: CategoryWithItems[] = []): AdminMenu {
  return { categories };
}

export function category(
  overrides: Partial<CategoryWithItems> = {},
): CategoryWithItems {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    name: 'Starters',
    description: null,
    position: 0,
    is_visible: true,
    created_at: '2026-07-21T00:00:00Z',
    updated_at: '2026-07-21T00:00:00Z',
    items: [],
    ...overrides,
  };
}

export function item(overrides: Partial<ItemSummary> = {}): ItemSummary {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    category_id: '11111111-1111-4111-8111-111111111111',
    name: 'Samosa',
    description: null,
    price_minor: 350,
    position: 0,
    is_available: true,
    is_hidden: false,
    is_featured: false,
    dietary_tags: [],
    image_media_id: null,
    image_alt_text: null,
    created_at: '2026-07-21T00:00:00Z',
    updated_at: '2026-07-21T00:00:00Z',
    ...overrides,
  };
}

/**
 * A complete-enough fake client. Defaults are the backend's neutral
 * failures so every success path must be scripted explicitly by the test.
 */
export function makeClient(overrides: ClientOverrides = {}): ApiClient {
  const fake = {
    auth: {
      login: vi.fn(async () =>
        apiError(401, envelope('unauthorized', 'Invalid email or password.')),
      ),
      logout: vi.fn(async () => ok({ status: 'logged_out' as const })),
      getSession: vi.fn(async () =>
        apiError(401, envelope('unauthorized', 'Authentication required.')),
      ),
      ...overrides.auth,
    },
    invitations: {
      preview: vi.fn(async () =>
        apiError(404, envelope('not_found', INVALID_INVITATION)),
      ),
      accept: vi.fn(async () =>
        apiError(404, envelope('not_found', INVALID_INVITATION)),
      ),
      acceptExisting: vi.fn(async () =>
        apiError(404, envelope('not_found', INVALID_INVITATION)),
      ),
      ...overrides.invitations,
    },
    passwordResets: {
      redeem: vi.fn(async () =>
        apiError(404, envelope('not_found', INVALID_RESET)),
      ),
      ...overrides.passwordResets,
    },
    platform: {
      // Neutral denial defaults: success paths must be scripted per test.
      createBusiness: vi.fn(async () => deniedPlatform()),
      listBusinesses: vi.fn(async () => deniedPlatform()),
      getBusiness: vi.fn(async () => deniedPlatform()),
      activate: vi.fn(async () => deniedPlatform()),
      suspend: vi.fn(async () => deniedPlatform()),
      reactivate: vi.fn(async () => deniedPlatform()),
      close: vi.fn(async () => deniedPlatform()),
      createInvitation: vi.fn(async () => deniedPlatform()),
      listInvitations: vi.fn(async () => deniedPlatform()),
      revokeInvitation: vi.fn(async () => deniedPlatform()),
      setEntitlements: vi.fn(async () => deniedPlatform()),
      issuePasswordReset: vi.fn(async () => deniedPlatform()),
      listAuditEvents: vi.fn(async () => deniedPlatform()),
      ...overrides.platform,
    },
    businesses: {
      // Neutral denial defaults across the business surface too: a test that
      // means to exercise a success path must say so.
      get: vi.fn(async () => neutralNotFound()),
      getEntitlements: vi.fn(async () => neutralNotFound()),
      createInvitation: vi.fn(async () => neutralNotFound()),
      listInvitations: vi.fn(async () => neutralNotFound()),
      revokeInvitation: vi.fn(async () => neutralNotFound()),
      listAuditEvents: vi.fn(async () => neutralNotFound()),
      ...overrides.businesses,
    },
    catalog: {
      getMenu: vi.fn(async () => neutralNotFound()),
      createCategory: vi.fn(async () => neutralNotFound()),
      updateCategory: vi.fn(async () => neutralNotFound()),
      deleteCategory: vi.fn(async () => neutralNotFound()),
      reorderCategories: vi.fn(async () => neutralNotFound()),
      createItem: vi.fn(async () => neutralNotFound()),
      getItem: vi.fn(async () => neutralNotFound()),
      updateItem: vi.fn(async () => neutralNotFound()),
      deleteItem: vi.fn(async () => neutralNotFound()),
      reorderItems: vi.fn(async () => neutralNotFound()),
      setItemAvailability: vi.fn(async () => neutralNotFound()),
      setItemImage: vi.fn(async () => neutralNotFound()),
      getModifierGroups: vi.fn(async () => neutralNotFound()),
      createModifierGroup: vi.fn(async () => neutralNotFound()),
      updateModifierGroup: vi.fn(async () => neutralNotFound()),
      deleteModifierGroup: vi.fn(async () => neutralNotFound()),
      reorderModifierGroups: vi.fn(async () => neutralNotFound()),
      createModifierOption: vi.fn(async () => neutralNotFound()),
      updateModifierOption: vi.fn(async () => neutralNotFound()),
      deleteModifierOption: vi.fn(async () => neutralNotFound()),
      reorderModifierOptions: vi.fn(async () => neutralNotFound()),
      ...overrides.catalog,
    },
    media: {
      uploadAsset: vi.fn(async () => neutralNotFound()),
      listAssets: vi.fn(async () => neutralNotFound()),
      getAsset: vi.fn(async () => neutralNotFound()),
      deleteAsset: vi.fn(async () => neutralNotFound()),
      fileUrl: (businessId: string, assetId: string, variant: string) =>
        `/api/v1/businesses/${businessId}/media/${assetId}/file/${variant}`,
      ...overrides.media,
    },
    // A surface the control center never touches; present so accidental use
    // fails loudly rather than silently returning undefined.
    public: {},
  };
  return fake as unknown as ApiClient;
}

function deniedPlatform(): ApiResult<never> {
  return apiError(
    403,
    envelope('permission_denied', 'You do not have permission to do that.'),
  );
}

/**
 * The backend's non-disclosure default for business-scoped routes: a
 * nonmember, a foreign tenant, and a nonexistent id are all this response.
 */
function neutralNotFound(): ApiResult<never> {
  return apiError(404, envelope('not_found', 'Not found.'));
}
