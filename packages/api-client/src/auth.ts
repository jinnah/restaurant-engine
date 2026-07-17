// Authentication facade (M2A, ADR-010).
//
// The session travels in an HttpOnly cookie the page can never read —
// the internal client sends credentials on every call. The CSRF
// synchronizer token from login/getSession must be passed back
// explicitly on unsafe calls (logout here; more from M2B).

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type LoginRequest = components['schemas']['LoginRequest'];
export type SessionResponse = components['schemas']['SessionResponse'];
export type LogoutResponse = components['schemas']['LogoutResponse'];
export type UserSummary = components['schemas']['UserSummary'];

export interface AuthApi {
  /** Authenticate; on success the browser stores the session cookie. */
  login(body: LoginRequest): Promise<ApiResult<SessionResponse>>;
  /** Revoke the current session. Requires the CSRF token (ADR-010). */
  logout(csrfToken: string): Promise<ApiResult<LogoutResponse>>;
  /** Current identity + a fresh CSRF token, from the session cookie. */
  getSession(): Promise<ApiResult<SessionResponse>>;
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

    async getSession(): Promise<ApiResult<SessionResponse>> {
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
