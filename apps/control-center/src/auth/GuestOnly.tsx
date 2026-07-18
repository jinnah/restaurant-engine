import { Navigate, Outlet, useSearchParams } from 'react-router';
import {
  BootstrapErrorPanel,
  SessionPending,
} from '../components/StatusPanels';
import { sanitizeNext } from './redirect';
import { useSession } from './useSession';

/**
 * Layout guard for guest-only routes (login). Loading renders the
 * neutral pending state so the form cannot flash for an authenticated
 * user; authenticated visitors are sent to their sanitized destination.
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
    return <Navigate to={sanitizeNext(params.get('next'))} replace />;
  }
  return <Outlet />;
}
