import { Navigate, Outlet, useLocation } from 'react-router';
import {
  BootstrapErrorPanel,
  SessionPending,
} from '../components/StatusPanels';
import { useSession } from './useSession';

/**
 * Layout guard for authenticated routes. A UX convenience only — the API
 * remains the authorization authority (docs/02 §control center). While
 * the session is loading nothing protected renders; anonymous visitors
 * are sent to /login with their intended internal path preserved.
 */
export function RequireAuth() {
  const session = useSession();
  const location = useLocation();

  if (session.status === 'loading') {
    return <SessionPending />;
  }
  if (session.status === 'error') {
    return <BootstrapErrorPanel retry={session.retry} />;
  }
  if (session.status === 'anonymous') {
    const intended = location.pathname + location.search;
    const target =
      intended === '/'
        ? '/login'
        : '/login?next=' + encodeURIComponent(intended);
    return <Navigate to={target} replace />;
  }
  return <Outlet />;
}
