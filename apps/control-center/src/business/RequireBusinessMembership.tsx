import { Outlet } from 'react-router';
import { useSession } from '../auth/useSession';
import { NotFoundPage } from '../routes/NotFoundPage';
import { findMembership, useCurrentBusinessId } from './useCurrentBusinessId';

/**
 * Layout guard for the business workspace (ADR-018).
 *
 * A route business the session holds no membership for renders the standard
 * not-found experience — presentation only, matching what the backend
 * independently returns to any nonmember (including platform administrators,
 * who hold no memberships). The copy never distinguishes a business that
 * does not exist from one that is not yours; that non-disclosure is the
 * contract, and repeating it here is the whole point.
 *
 * The guard is also why no catalog request is issued for a business the
 * session does not contain — a usability nicety, never the boundary.
 */
export function RequireBusinessMembership() {
  const session = useSession();
  const businessId = useCurrentBusinessId();

  if (session.status !== 'authenticated') {
    return null; // RequireAuth owns every other state.
  }
  if (findMembership(session.session.memberships, businessId) === null) {
    return <NotFoundPage />;
  }
  return <Outlet />;
}
