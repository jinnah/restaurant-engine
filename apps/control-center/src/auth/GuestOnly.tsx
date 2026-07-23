import { Navigate, Outlet, useSearchParams } from 'react-router';
import {
  BootstrapErrorPanel,
  SessionPending,
} from '../components/StatusPanels';
import { landingPath } from './landing';
import { useSession } from './useSession';

/**
 * Layout guard for guest-only routes (login). Loading renders the
 * neutral pending state so the form cannot flash for an authenticated
 * user; an already-authenticated visitor is sent to their role-appropriate
 * landing — an intended deep link when they can reach it, otherwise their
 * own home rather than Page Not Found (item 2).
 */
export function GuestOnly() {
  const session = useSession();
  const [params] = useSearchParams();

  if (session.status === 'loading') {
    return <SessionPending />;
  }
  if (session.status === 'error') {
    return <BootstrapErrorPanel retry={session.retry} />;
  }
  if (session.status === 'authenticated') {
    return (
      <Navigate to={landingPath(params.get('next'), session.session)} replace />
    );
  }
  return <Outlet />;
}
