import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import type { SessionView } from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { ApiFailure, asApiFailure, unwrap } from '../api/failure';
import { currentCsrfToken } from '../auth/csrf';
import { clearAuthenticatedState, establishSession } from '../auth/session';
import { useLogout } from '../auth/useLogout';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary } from '../components/StatusPanels';
import { InvitationPreviewCard, TokenField } from './invitationShared';
import styles from './authForms.module.css';

const PREVIEW_FALLBACK = 'This invitation cannot be used.';
const ACCEPT_FALLBACK = 'The invitation could not be accepted.';

// Acceptance is irreversible (the token is consumed), so every state
// after it succeeds is terminal for the token: refresh problems offer
// session recovery only, never a path back to a resubmittable form.
type Phase =
  'token' | 'confirm' | 'refreshing' | 'refreshFailed' | 'membershipMissing';

/**
 * Authenticated acceptance (ADR-015): preview → explicit confirmation →
 * accept with the call-time CSRF token → terminal refresh of the
 * authoritative session, confirming the new membership by the safe
 * `business_id` the acceptance response returned.
 */
export function ExistingAcceptFlow({ session }: { session: SessionView }) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const logout = useLogout();

  const [phase, setPhase] = useState<Phase>('token');
  const [token, setToken] = useState('');
  // The safe business id from the acceptance response — the only datum
  // retained after acceptance, held in a ref so the immediately-triggered
  // session refresh can never read a stale value.
  const acceptedBusinessIdRef = useRef<string | null>(null);
  const [failure, setFailure] = useState<FormFailure | null>(null);

  const preview = useMutation({
    // Variables-free: the token lives only in component state (hygiene).
    mutationFn: async () => unwrap(await client.invitations.preview({ token })),
    onSuccess: () => {
      setFailure(null);
      setPhase('confirm');
    },
    onError: (error: unknown) => {
      setFailure(mapFailure(asApiFailure(error), PREVIEW_FALLBACK));
    },
  });

  const accept = useMutation({
    mutationFn: async () => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(null, null);
      }
      const result = await client.invitations.acceptExisting(
        { token },
        csrfToken,
      );
      if (!result.ok && result.status === 401) {
        // Privileged 401: the session died mid-flow. Clear authenticated
        // state immediately (no refetch loop); the page re-gates.
        await clearAuthenticatedState(queryClient);
      }
      return unwrap(result);
    },
    onSuccess: (data) => {
      acceptedBusinessIdRef.current = String(data.business_id);
      setToken('');
      setFailure(null);
      setPhase('refreshing');
      refresh.mutate();
    },
    onError: (error: unknown) => {
      setFailure(mapFailure(asApiFailure(error), ACCEPT_FALLBACK));
    },
  });

  const refresh = useMutation({
    mutationFn: () => establishSession(client, queryClient),
    onSuccess: (state) => {
      const acceptedId = acceptedBusinessIdRef.current;
      const present =
        acceptedId !== null &&
        state.kind === 'authenticated' &&
        state.session.memberships.some(
          (item) => item.business_id === acceptedId,
        );
      if (present) {
        void navigate('/', { replace: true });
      } else {
        setPhase('membershipMissing');
      }
    },
    onError: () => {
      setPhase('refreshFailed');
    },
  });

  // Terminal cleanup: once acceptance succeeded, no token-bearing
  // mutation retains state (only the safe accepted business id survives,
  // in a ref, for membership confirmation).
  useEffect(() => {
    if (phase === 'refreshing') {
      preview.reset();
      accept.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset functions are stable
  }, [phase]);

  function submitToken(event: FormEvent) {
    event.preventDefault();
    if (preview.isPending) return;
    setFailure(null);
    preview.mutate();
  }

  if (phase === 'refreshing' || phase === 'refreshFailed') {
    return (
      <section className={styles.card}>
        {phase === 'refreshFailed' ? (
          <>
            <div role="alert">
              <h1>Invitation accepted</h1>
              <p>
                The invitation was accepted, but we could not refresh your
                session. Your new membership is safe — retry loading your
                session below.
              </p>
            </div>
            <button
              type="button"
              className={styles.submit}
              onClick={() => {
                refresh.reset();
                refresh.mutate();
              }}
            >
              Retry loading session
            </button>
          </>
        ) : (
          <p role="status">Invitation accepted. Refreshing your session…</p>
        )}
      </section>
    );
  }

  if (phase === 'membershipMissing') {
    return (
      <section className={styles.card}>
        <div role="alert">
          <h1>Invitation accepted</h1>
          <p>
            The invitation was accepted, but the new membership has not appeared
            in your session yet. Refresh your session, or sign out and sign back
            in.
          </p>
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.submit}
            onClick={() => {
              refresh.reset();
              refresh.mutate();
            }}
          >
            Refresh session
          </button>
          <button
            type="button"
            className={styles.secondary}
            disabled={logout.isPending}
            onClick={() => {
              logout.mutate();
            }}
          >
            Sign out
          </button>
        </div>
      </section>
    );
  }

  if (phase === 'confirm' && preview.data !== undefined) {
    return (
      <section className={styles.card} aria-labelledby="accept-confirm-title">
        <h1 id="accept-confirm-title">Join this business?</h1>
        <InvitationPreviewCard preview={preview.data} />
        <p>
          You are signed in as <strong>{session.user.email}</strong>. Accept to
          join <strong>{preview.data.business_name}</strong> as{' '}
          <strong>{preview.data.role}</strong> with this account.
        </p>
        {failure !== null && <ErrorSummary message={failure.summary} />}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.submit}
            disabled={accept.isPending}
            onClick={() => {
              if (!accept.isPending) accept.mutate();
            }}
          >
            {accept.isPending ? 'Joining…' : 'Accept invitation'}
          </button>
          <button
            type="button"
            className={styles.secondary}
            disabled={accept.isPending}
            onClick={() => {
              setToken('');
              setFailure(null);
              preview.reset();
              setPhase('token');
            }}
          >
            Use a different token
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.card} aria-labelledby="accept-existing-title">
      <h1 id="accept-existing-title">Accept an invitation</h1>
      <p className={styles.lede}>
        You are signed in as <strong>{session.user.email}</strong>. Paste the
        invitation token to add its business to this account.
      </p>
      {failure !== null && <ErrorSummary message={failure.summary} />}
      <form noValidate onSubmit={submitToken}>
        <TokenField
          id="accept-existing-token"
          label="Invitation token"
          value={token}
          onChange={setToken}
        />
        <button
          type="submit"
          className={styles.submit}
          disabled={preview.isPending}
        >
          {preview.isPending ? 'Checking…' : 'Continue'}
        </button>
      </form>
    </section>
  );
}
