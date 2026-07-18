import { useEffect } from 'react';
import {
  BootstrapErrorPanel,
  SessionPending,
} from '../components/StatusPanels';
import { useSession } from '../auth/useSession';
import { ExistingAcceptFlow } from './ExistingAcceptFlow';
import { GuestAcceptFlow } from './GuestAcceptFlow';

/**
 * Public accept-invitation route, session-aware (ADR-015): the flow is
 * chosen only once session bootstrap resolves, so the wrong form can
 * never flash. The expected anonymous 401 selects the new-user flow; an
 * authenticated session selects existing-user acceptance; an unexpected
 * bootstrap failure is a distinct retryable state.
 */
export function AcceptInvitationPage() {
  const session = useSession();

  useEffect(() => {
    document.title = 'Accept invitation — Restaurant Engine';
  }, []);

  if (session.status === 'loading') {
    return <SessionPending />;
  }
  if (session.status === 'error') {
    return <BootstrapErrorPanel retry={session.retry} />;
  }
  return session.status === 'authenticated' ? (
    <ExistingAcceptFlow session={session.session} />
  ) : (
    <GuestAcceptFlow />
  );
}
