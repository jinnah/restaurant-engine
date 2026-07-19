import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router';
import { useApiClient } from '../api/ClientProvider';
import { asApiFailure, unwrap } from '../api/failure';
import { clearAuthenticatedState } from '../auth/session';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary, SuccessPanel } from '../components/StatusPanels';
import { TokenField } from './invitationShared';
import styles from './authForms.module.css';

const REDEEM_FALLBACK = 'The reset token could not be used.';

/**
 * Public password-reset redemption (ADR-015). Always the public
 * contract — an existing session cookie never switches this page to an
 * authenticated mutation. Success clears every trace of cached
 * authenticated state (the backend revoked all sessions) and never
 * implies the visitor was signed in.
 */
export function PasswordResetPage() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const [done, setDone] = useState(false);
  const [token, setToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [failure, setFailure] = useState<FormFailure | null>(null);

  useEffect(() => {
    document.title = 'Reset password — Restaurant Engine';
  }, []);

  const redeem = useMutation({
    // Variables-free: token and password live only in component state.
    mutationFn: async () => {
      const data = unwrap(
        await client.passwordResets.redeem({
          token,
          new_password: newPassword,
        }),
      );
      // The backend revoked every session for this account; a previously
      // authenticated tab must stop rendering authenticated state now.
      await clearAuthenticatedState(queryClient);
      return data;
    },
    onSuccess: () => {
      setToken('');
      setNewPassword('');
      setConfirmPassword('');
      setFailure(null);
      setDone(true);
    },
    onError: (error: unknown) => {
      setFailure(mapFailure(asApiFailure(error), REDEEM_FALLBACK));
    },
  });

  // Terminal cleanup: the consumed token is retained nowhere, and no
  // path can resubmit it.
  useEffect(() => {
    if (done) {
      redeem.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset is stable
  }, [done]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (redeem.isPending) return;
    if (newPassword !== confirmPassword) {
      setFailure({
        summary: 'Passwords do not match.',
        fields: { confirm_password: 'Enter the same password again.' },
      });
      return;
    }
    setFailure(null);
    redeem.mutate();
  }

  if (done) {
    return (
      <section className={styles.card}>
        <SuccessPanel heading="Password changed">
          <p>
            Your password was changed and every existing session was signed out.
            You are <strong>not</strong> signed in — sign in with your new
            password.
          </p>
          <Link to="/login">Go to sign in</Link>
        </SuccessPanel>
      </section>
    );
  }

  return (
    <section className={styles.card} aria-labelledby="reset-title">
      <h1 id="reset-title">Reset your password</h1>
      <p className={styles.lede}>
        Paste the reset token you received and choose a new password.
      </p>
      {failure !== null && <ErrorSummary failure={failure} />}
      <form noValidate onSubmit={onSubmit}>
        <TokenField
          id="reset-token"
          label="Reset token"
          value={token}
          onChange={setToken}
          error={failure?.fields['token']}
        />
        <div className={styles.field}>
          <label htmlFor="reset-new-password">New password</label>
          <input
            id="reset-new-password"
            name="new_password"
            type="password"
            autoComplete="new-password"
            required
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            aria-invalid={failure?.fields['new_password'] !== undefined}
            aria-describedby={
              failure?.fields['new_password'] !== undefined
                ? 'reset-new-password-error'
                : undefined
            }
          />
          {failure?.fields['new_password'] !== undefined && (
            <p id="reset-new-password-error" className={styles.fieldError}>
              {failure.fields['new_password']}
            </p>
          )}
        </div>
        <div className={styles.field}>
          <label htmlFor="reset-confirm-password">Confirm new password</label>
          <input
            id="reset-confirm-password"
            name="confirm_password"
            type="password"
            autoComplete="new-password"
            required
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            aria-invalid={failure?.fields['confirm_password'] !== undefined}
            aria-describedby={
              failure?.fields['confirm_password'] !== undefined
                ? 'reset-confirm-password-error'
                : undefined
            }
          />
          {failure?.fields['confirm_password'] !== undefined && (
            <p id="reset-confirm-password-error" className={styles.fieldError}>
              {failure.fields['confirm_password']}
            </p>
          )}
        </div>
        <button
          type="submit"
          className={styles.submit}
          disabled={redeem.isPending}
        >
          {redeem.isPending ? 'Changing password…' : 'Change password'}
        </button>
      </form>
    </section>
  );
}
