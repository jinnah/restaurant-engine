import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { PasswordResetIssueResponse } from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { ApiFailure, asApiFailure } from '../api/failure';
import { currentCsrfToken } from '../auth/csrf';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary } from '../components/StatusPanels';
import { unwrapPrivileged } from './api';
import { FormField } from './FormField';
import { OneTimeTokenReveal } from './OneTimeTokenReveal';
import styles from './platform.module.css';

/**
 * Platform-issued password recovery (ADR-014): issuing a reset token is
 * account-takeover-equivalent authority — every issuance is audited,
 * and the raw token appears exactly once, here, in transient state.
 */
export function RecoveryPage() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  const [email, setEmail] = useState('');
  const [failure, setFailure] = useState<FormFailure | null>(null);
  const [issued, setIssued] = useState<PasswordResetIssueResponse | null>(null);

  useEffect(() => {
    document.title = 'Recovery — Restaurant Engine';
  }, []);

  const issue = useMutation({
    mutationFn: async (body: { email: string }) => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(401, null);
      }
      return unwrapPrivileged(
        queryClient,
        await client.platform.issuePasswordReset(body, csrfToken),
      );
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (issue.isPending) {
      return;
    }
    // A new attempt immediately discards any previously revealed token.
    setIssued(null);
    setFailure(null);
    issue.mutate(
      { email },
      {
        onSuccess: (response) => {
          setEmail('');
          setIssued(response);
        },
        onError: (error: unknown) => {
          setFailure(
            mapFailure(
              asApiFailure(error),
              'The reset token could not be issued.',
            ),
          );
        },
      },
    );
  }

  return (
    <section className={styles.section} aria-labelledby="recovery-title">
      <h2 id="recovery-title">Account recovery</h2>
      <p className={styles.hint}>
        Issuing a reset token gives its holder control of the account: it is the
        same authority as taking the account over, and every issuance is
        recorded in the audit trail. Verify who you are talking to before
        issuing, and deliver the token only to the account holder.
      </p>
      {failure !== null && <ErrorSummary failure={failure} />}
      {issued !== null && (
        <OneTimeTokenReveal
          token={issued.token}
          heading="Reset token issued"
          onDismiss={() => {
            setIssued(null);
          }}
        >
          <p>
            For <strong>{issued.email}</strong>, valid until{' '}
            {new Date(issued.expires_at).toLocaleString()}. The account holder
            redeems it on the password-reset page; redeeming signs out every
            existing session.
          </p>
        </OneTimeTokenReveal>
      )}
      <form noValidate onSubmit={onSubmit}>
        <FormField
          id="recovery-email"
          label="Account email"
          name="email"
          type="email"
          autoComplete="off"
          required
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
          }}
          error={failure?.fields['email']}
        />
        <button
          type="submit"
          className={styles.submit}
          disabled={issue.isPending}
        >
          {issue.isPending ? 'Issuing…' : 'Issue reset token'}
        </button>
      </form>
    </section>
  );
}
