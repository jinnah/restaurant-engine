import type { MembershipSummary } from '@restaurant-engine/api-client';

/**
 * What the current member can be *offered* on the order board (M7C,
 * ADR-027). Every role operates orders — reads and the transition
 * commands ride the one D2 capability (`business.orders.operate`),
 * granted to owner, manager, AND staff — so unlike the storefront there
 * is no read gate at all. Pausing ordering is hours-owned state
 * (`business.hours.write`, ruling D8), so the pause control is
 * owner/manager only. As everywhere, these derivations are usability
 * aids — the service re-checks capability on every request.
 */
export interface OrdersPermissions {
  /** Offer the pause/resume control (hours-write authority, D8). */
  canPause: boolean;
}

export function ordersPermissions(
  membership: MembershipSummary,
): OrdersPermissions {
  const manages = membership.role === 'owner' || membership.role === 'manager';
  return { canPause: manages && membership.business_status !== 'closed' };
}
