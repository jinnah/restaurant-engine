// Public invitation-redemption facade (M2D, ADR-014).
//
// Tokens travel ONLY in POST bodies — never URLs or query strings. The
// facade takes no tenant selector of any kind: the invitation token binds
// the business, email, and role server-side. `accept` creates the account
// without logging in (the caller uses auth.login afterwards);
// `acceptExisting` is cookie-authenticated and needs the CSRF token.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type InvitationPreviewRequest =
  components['schemas']['InvitationPreviewRequest'];
export type InvitationPreviewResponse =
  components['schemas']['InvitationPreviewResponse'];
export type InvitationAcceptRequest =
  components['schemas']['InvitationAcceptRequest'];
export type InvitationAcceptExistingRequest =
  components['schemas']['InvitationAcceptExistingRequest'];
export type InvitationAcceptedResponse =
  components['schemas']['InvitationAcceptedResponse'];

const CSRF_HEADER = 'X-CSRF-Token';

export interface InvitationsApi {
  /** Accept-page context: business name, role, masked email hint. */
  preview(
    body: InvitationPreviewRequest,
  ): Promise<ApiResult<InvitationPreviewResponse>>;
  /** Create the invited account + membership. No auto-login. */
  accept(
    body: InvitationAcceptRequest,
  ): Promise<ApiResult<InvitationAcceptedResponse>>;
  /** Add the invited membership to the signed-in account (CSRF required). */
  acceptExisting(
    body: InvitationAcceptExistingRequest,
    csrfToken: string,
  ): Promise<ApiResult<InvitationAcceptedResponse>>;
}

export function createInvitationsApi(client: Client<paths>): InvitationsApi {
  return {
    async preview(body) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/invitations/preview',
          { body },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async accept(body) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/invitations/accept',
          { body },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async acceptExisting(body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/invitations/accept-existing',
          { body, headers: { [CSRF_HEADER]: csrfToken } },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
