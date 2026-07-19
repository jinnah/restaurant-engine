import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router';
import { useApiClient } from '../api/ClientProvider';
import { asApiFailure, unwrap } from '../api/failure';
import { sanitizeNext } from '../auth/redirect';
import { establishSession } from '../auth/session';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary } from '../components/StatusPanels';
import styles from './authForms.module.css';

const LOGIN_FALLBACK = 'Sign-in failed. Please try again.';

export function LoginPage() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [failure, setFailure] = useState<FormFailure | null>(null);

  useEffect(() => {
    document.title = 'Sign in — Restaurant Engine';
  }, []);

  // Authoritative session establishment (ADR-015): the login response is
  // never cached as the session. After login succeeds we fetch
  // GET /auth/session, populate the cache only from it, and navigate only
  // once that succeeds. Its failure state retries the session fetch alone
  // — credentials are never resubmitted automatically.
  const establish = useMutation({
    mutationFn: () => establishSession(client, queryClient),
    onSuccess: () => {
      void navigate(sanitizeNext(params.get('next')), { replace: true });
    },
  });

  const login = useMutation({
    mutationFn: async (body: { email: string; password: string }) =>
      unwrap(await client.auth.login(body)),
    onSuccess: () => {
      setFailure(null);
      establish.mutate();
    },
    onError: (error: unknown) => {
      setFailure(mapFailure(asApiFailure(error), LOGIN_FALLBACK));
    },
  });

  const submitting = login.isPending || establish.isPending;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setFailure(null);
    login.mutate({ email, password });
  }

  if (establish.isError) {
    return (
      <section className={styles.card} aria-labelledby="login-establish-title">
        <div role="alert">
          <h1 id="login-establish-title">Signed in, but something failed</h1>
          <p>
            Your sign-in succeeded, but your session could not be loaded. No one
            else can use it — you can safely try again.
          </p>
        </div>
        <button
          type="button"
          className={styles.submit}
          onClick={() => {
            establish.reset();
            establish.mutate();
          }}
        >
          Retry loading session
        </button>
      </section>
    );
  }

  return (
    <section className={styles.card} aria-labelledby="login-title">
      <h1 id="login-title">Sign in</h1>
      <p className={styles.lede}>Control center for Restaurant Engine.</p>
      {failure !== null && <ErrorSummary failure={failure} />}
      <form noValidate onSubmit={onSubmit}>
        <div className={styles.field}>
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            aria-invalid={failure?.fields['email'] !== undefined}
            aria-describedby={
              failure?.fields['email'] !== undefined
                ? 'login-email-error'
                : undefined
            }
          />
          {failure?.fields['email'] !== undefined && (
            <p id="login-email-error" className={styles.fieldError}>
              {failure.fields['email']}
            </p>
          )}
        </div>
        <div className={styles.field}>
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={failure?.fields['password'] !== undefined}
            aria-describedby={
              failure?.fields['password'] !== undefined
                ? 'login-password-error'
                : undefined
            }
          />
          {failure?.fields['password'] !== undefined && (
            <p id="login-password-error" className={styles.fieldError}>
              {failure.fields['password']}
            </p>
          )}
        </div>
        <button type="submit" className={styles.submit} disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </section>
  );
}
