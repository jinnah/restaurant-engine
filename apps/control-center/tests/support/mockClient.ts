// Injected fake for the generated facade (ADR-009): tests exercise the
// real routes and components with a typed, per-test scripted client.

import { vi } from 'vitest';
import type {
  ApiClient,
  ApiResult,
  BusinessSummary,
  ErrorEnvelope,
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
    // Surfaces the control center never touches as an admin; present so
    // accidental use fails loudly.
    businesses: {},
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
