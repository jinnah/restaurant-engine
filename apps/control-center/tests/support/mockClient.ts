// Injected fake for the generated facade (ADR-009): tests exercise the
// real routes and components with a typed, per-test scripted client.

import { vi } from 'vitest';
import type {
  ApiClient,
  ApiResult,
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

export interface ClientOverrides {
  auth?: Partial<ApiClient['auth']>;
  invitations?: Partial<ApiClient['invitations']>;
  passwordResets?: Partial<ApiClient['passwordResets']>;
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
    // Surfaces M2E never touches; present so accidental use fails loudly.
    platform: {},
    businesses: {},
    public: {},
  };
  return fake as unknown as ApiClient;
}
