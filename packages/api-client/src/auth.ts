// Authentication facade (M2A, ADR-010; M2B session view).
//
// The session travels in an HttpOnly cookie the page can never read —
// the internal client sends credentials on every call. The CSRF
// synchronizer token from login/getSession must be passed back
// explicitly on unsafe calls (logout here; platform commands from M2B).

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type LoginRequest = components['schemas']['LoginRequest'];
// login stays lean (identity-only). getSession returns the enriched view
// composed at the application layer: adds the caller's memberships (M2B).
export type SessionResponse = components['schemas']['SessionResponse'];
export type SessionView = components['schemas']['SessionView'];
export type MembershipSummary = components['schemas']['MembershipSummary'];
export type LogoutResponse = components['schemas']['LogoutResponse'];
export type UserSummary = components['schemas']['UserSummary'];

export interface AuthApi {
  /** Authenticate; on success the browser stores the session cookie. */
  login(body: LoginRequest): Promise<ApiResult<SessionResponse>>;
  /** Revoke the current session. Requires the CSRF token (ADR-010). */
  logout(csrfToken: string): Promise<ApiResult<LogoutResponse>>;
  /** Current identity, CSRF token, and the caller's business memberships. */
  getSession(): Promise<ApiResult<SessionView>>;
}

export function createAuthApi(client: Client<paths>): AuthApi {
  return {
    async login(body: LoginRequest): Promise<ApiResult<SessionResponse>> {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/auth/login',
          { body },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async logout(csrfToken: string): Promise<ApiResult<LogoutResponse>> {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/auth/logout',
          { headers: { 'X-CSRF-Token': csrfToken } },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getSession(): Promise<ApiResult<SessionView>> {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/auth/session',
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
