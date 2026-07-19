import type { AuditListParams } from '@restaurant-engine/api-client';

export interface PageParams {
  limit: number;
  offset: number;
}

/**
 * Platform query keys (ADR-016). All are feature-scoped under
 * 'platform' — distinct from the canonical ['session'] key — so
 * clearAuthenticatedState's remove-everything-but-session predicate
 * covers them without special cases.
 */
export const platformKeys = {
  businesses: (page: PageParams) => ['platform', 'businesses', page] as const,
  allBusinesses: () => ['platform', 'businesses'] as const,
  business: (businessId: string) =>
    ['platform', 'business', businessId] as const,
  invitations: (businessId: string, page: PageParams) =>
    ['platform', 'invitations', businessId, page] as const,
  allInvitations: (businessId: string) =>
    ['platform', 'invitations', businessId] as const,
  audit: (filters: AuditListParams & { businessId?: string }) =>
    ['platform', 'audit', filters] as const,
};
