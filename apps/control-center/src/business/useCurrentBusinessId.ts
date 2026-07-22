import { useMatch } from 'react-router';
import type { MembershipSummary } from '@restaurant-engine/api-client';

/**
 * The business the user is currently working in, derived from the route.
 *
 * There is deliberately no current-business state, context, or storage
 * (ADR-018 ruling 2). The URL is the single source of truth, so the switcher
 * in the chrome and the workspace below it can never disagree, and a
 * refreshed or shared link lands exactly where it says it does.
 *
 * Returns null outside a workspace route.
 */
export function useCurrentBusinessId(): string | null {
  const match = useMatch('/businesses/:businessId/*');
  return match?.params.businessId ?? null;
}

/**
 * The caller's membership for a business, or null when the session holds
 * none. A UX lookup only — the backend independently returns 404 to any
 * nonmember, including platform administrators (docs/04).
 */
export function findMembership(
  memberships: MembershipSummary[],
  businessId: string | null,
): MembershipSummary | null {
  if (businessId === null) {
    return null;
  }
  return (
    memberships.find((membership) => membership.business_id === businessId) ??
    null
  );
}
