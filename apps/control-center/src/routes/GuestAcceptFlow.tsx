import { useEffect, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link } from 'react-router';
import { useApiClient } from '../api/ClientProvider';
import { asApiFailure, unwrap } from '../api/failure';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary, SuccessPanel } from '../components/StatusPanels';
import { InvitationPreviewCard, TokenField } from './invitationShared';
import styles from './authForms.module.css';

const PREVIEW_FALLBACK = 'This invitation cannot be used.';
const ACCEPT_FALLBACK = 'The invitation could not be accepted.';

type Phase = 'token' | 'details' | 'done';

/**
 * New-user acceptance (ADR-015): paste token → preview (POST body) →
 * display name + password → accept. Success never signs the visitor in;
 * all sensitive fields and token-bearing mutation state are cleared.
 */
export function GuestAcceptFlow() {
  const client = useApiClient();

  const [phase, setPhase] = useState<Phase>('token');
  const [token, setToken] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [failure, setFailure] = useState<FormFailure | null>(null);

  const preview = useMutation({
    // Variables-free by design: the token stays in component state, so no
    // mutation retains it after reset (ADR-015 token hygiene).
    mutationFn: async () => unwrap(await client.invitations.preview({ token })),
    onSuccess: () => {
      setFailure(null);
      setPhase('details');
    },
    onError: (error: unknown) => {
      setFailure(mapFailure(asApiFailure(error), PREVIEW_FALLBACK));
    },
  });

  const accept = useMutation({
    mutationFn: async () =>
      unwrap(
        await client.invitations.accept({
          token,
          display_name: displayName,
          password,
        }),
      ),
    onSuccess: () => {
      setToken('');
      setDisplayName('');
      setPassword('');
      setConfirmPassword('');
      setFailure(null);
      setPhase('done');
    },
    onError: (error: unknown) => {
      setFailure(mapFailure(asApiFailure(error), ACCEPT_FALLBACK));
    },
  });

  // Terminal cleanup: once done, no mutation retains data about the
  // consumed token and there is no path that could resubmit it.
  useEffect(() => {
    if (phase === 'done') {
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

  function submitDetails(event: FormEvent) {
    event.preventDefault();
    if (accept.isPending) return;
    if (password !== confirmPassword) {
      setFailure({
        summary: 'Passwords do not match.',
        fields: { confirm_password: 'Enter the same password again.' },
      });
      return;
    }
    setFailure(null);
    accept.mutate();
  }

  if (phase === 'done') {
    return (
      <section className={styles.card}>
        <SuccessPanel heading="Invitation accepted">
          <p>
            Your account was created. You were <strong>not</strong> signed in —
            sign in with your email address and the password you just chose.
          </p>
          <Link to="/login">Go to sign in</Link>
        </SuccessPanel>
      </section>
    );
  }

  if (phase === 'details' && preview.data !== undefined) {
    return (
      <section className={styles.card} aria-labelledby="accept-details-title">
        <h1 id="accept-details-title">Create your account</h1>
        <InvitationPreviewCard preview={preview.data} />
        {failure !== null && <ErrorSummary failure={failure} />}
        <form noValidate onSubmit={submitDetails}>
          <div className={styles.field}>
            <label htmlFor="accept-display-name">Your name</label>
            <input
              id="accept-display-name"
              name="display_name"
              type="text"
              autoComplete="name"
              required
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              aria-invalid={failure?.fields['display_name'] !== undefined}
              aria-describedby={
                failure?.fields['display_name'] !== undefined
                  ? 'accept-display-name-error'
                  : undefined
              }
            />
            {failure?.fields['display_name'] !== undefined && (
              <p id="accept-display-name-error" className={styles.fieldError}>
                {failure.fields['display_name']}
              </p>
            )}
          </div>
          <div className={styles.field}>
            <label htmlFor="accept-password">Password</label>
            <input
              id="accept-password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={failure?.fields['password'] !== undefined}
              aria-describedby={
                failure?.fields['password'] !== undefined
                  ? 'accept-password-error'
                  : undefined
              }
            />
            {failure?.fields['password'] !== undefined && (
              <p id="accept-password-error" className={styles.fieldError}>
                {failure.fields['password']}
              </p>
            )}
          </div>
          <div className={styles.field}>
            <label htmlFor="accept-confirm-password">Confirm password</label>
            <input
              id="accept-confirm-password"
              name="confirm_password"
              type="password"
              autoComplete="new-password"
              required
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              aria-invalid={failure?.fields['confirm_password'] !== undefined}
              aria-describedby={
                failure?.fields['confirm_password'] !== undefined
                  ? 'accept-confirm-password-error'
                  : undefined
              }
            />
            {failure?.fields['confirm_password'] !== undefined && (
              <p
                id="accept-confirm-password-error"
                className={styles.fieldError}
              >
                {failure.fields['confirm_password']}
              </p>
            )}
          </div>
          <button
            type="submit"
            className={styles.submit}
            disabled={accept.isPending}
          >
            {accept.isPending ? 'Accepting…' : 'Accept invitation'}
          </button>
        </form>
      </section>
    );
  }

  return (
    <section className={styles.card} aria-labelledby="accept-token-title">
      <h1 id="accept-token-title">Accept an invitation</h1>
      <p className={styles.lede}>
        Paste the invitation token you received to see the details.
      </p>
      {failure !== null && <ErrorSummary failure={failure} />}
      <form noValidate onSubmit={submitToken}>
        <TokenField
          id="accept-token"
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
