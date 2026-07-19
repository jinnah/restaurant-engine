import { Outlet } from 'react-router';
import { useSession } from '../auth/useSession';
import { NotFoundPage } from '../routes/NotFoundPage';

/**
 * Layout guard for the platform area (ADR-016): an authenticated
 * non-administrator receives the standard not-found experience —
 * presentation only, the backend capability checks stay authoritative.
 * Renders under RequireAuth, which owns loading/error/anonymous states.
 */
export function RequirePlatformAdmin() {
  const session = useSession();

  if (session.status !== 'authenticated') {
    return null; // RequireAuth owns every other state.
  }
  if (!session.session.user.is_platform_admin) {
    return <NotFoundPage />;
  }
  return <Outlet />;
}
