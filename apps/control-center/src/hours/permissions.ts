import type { MembershipSummary } from '@restaurant-engine/api-client';

/**
 * What the current member can be *offered* on the hours surface, derived
 * from role AND business lifecycle (ADR-025 ruling D7).
 *
 * Unlike the storefront (whose read staff deliberately lack), hours reads
 * ride on `business.view`: the schedule is public information and staff
 * see the hours they work, so the navigation entry exists for every role
 * and there is no `canRead` here. Writes are owner/manager
 * (`business.hours.write`); a closed business stays readable and refuses
 * every mutation. As everywhere, these derivations are usability aids —
 * the service re-checks capability and lifecycle on every request.
 */
export interface HoursPermissions {
  /** Edit and save the weekly schedule, exceptions, and fulfillment. */
  canEdit: boolean;
  /** Why the surface is read-only, for honest presentation. */
  readOnlyReason: 'closed' | 'role' | null;
}

export function hoursPermissions(
  membership: MembershipSummary,
): HoursPermissions {
  const closed = membership.business_status === 'closed';
  const manages = membership.role === 'owner' || membership.role === 'manager';
  if (closed) {
    return { canEdit: false, readOnlyReason: 'closed' };
  }
  if (!manages) {
    return { canEdit: false, readOnlyReason: 'role' };
  }
  return { canEdit: true, readOnlyReason: null };
}
