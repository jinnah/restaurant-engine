// Business-scoped member facade (M2B; M2D invitations/entitlements/audit).
//
// The caller acts on their own business; the server authorizes via
// membership capabilities. Nonmembers get 404 (existence non-disclosure).
// Invitation issuance returns the raw token exactly once for out-of-band
// delivery; list projections never carry token material.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import type { AuditListParams, BusinessSummary } from './platform';
import { toResult, type ApiResult } from './result';

export type InvitationCreate = components['schemas']['InvitationCreate'];
export type InvitationIssueResponse =
  components['schemas']['InvitationIssueResponse'];
export type InvitationPage = components['schemas']['InvitationPage'];
export type InvitationSummary = components['schemas']['InvitationSummary'];
export type InvitationRevokedResponse =
  components['schemas']['InvitationRevokedResponse'];
export type EntitlementsResponse =
  components['schemas']['EntitlementsResponse'];
export type AuditEventPage = components['schemas']['AuditEventPage'];
export type AuditEventSummary = components['schemas']['AuditEventSummary'];

const CSRF_HEADER = 'X-CSRF-Token';

export interface BusinessesApi {
  get(businessId: string): Promise<ApiResult<BusinessSummary>>;
  /** Invite a member (owner/manager; role ceiling applies server-side). */
  createInvitation(
    businessId: string,
    body: InvitationCreate,
    csrfToken: string,
  ): Promise<ApiResult<InvitationIssueResponse>>;
  /** Pending invitations (history lives in the audit trail). */
  listInvitations(
    businessId: string,
    params?: { limit?: number; offset?: number },
  ): Promise<ApiResult<InvitationPage>>;
  revokeInvitation(
    businessId: string,
    invitationId: string,
    csrfToken: string,
  ): Promise<ApiResult<InvitationRevokedResponse>>;
  /** The business's enabled features (any member). */
  getEntitlements(businessId: string): Promise<ApiResult<EntitlementsResponse>>;
  /** The business audit trail (owner/manager). */
  listAuditEvents(
    businessId: string,
    params?: AuditListParams,
  ): Promise<ApiResult<AuditEventPage>>;
}

export function createBusinessesApi(client: Client<paths>): BusinessesApi {
  const path = (businessId: string) => ({
    params: { path: { business_id: businessId } },
  });

  return {
    async get(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}',
          path(businessId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async createInvitation(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/invitations',
          {
            ...path(businessId),
            body,
            headers: { [CSRF_HEADER]: csrfToken },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async listInvitations(businessId, params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/invitations',
          {
            params: {
              path: { business_id: businessId },
              query: { limit: params?.limit, offset: params?.offset },
            },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async revokeInvitation(businessId, invitationId, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/invitations/{invitation_id}/revoke',
          {
            params: {
              path: { business_id: businessId, invitation_id: invitationId },
            },
            body: {},
            headers: { [CSRF_HEADER]: csrfToken },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getEntitlements(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/entitlements',
          path(businessId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async listAuditEvents(businessId, params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/audit-events',
          {
            params: {
              path: { business_id: businessId },
              query: {
                limit: params?.limit,
                before_id: params?.beforeId,
                action: params?.action,
                occurred_after: params?.occurredAfter,
                occurred_before: params?.occurredBefore,
              },
            },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
