import { useEffect, useRef, type ReactNode } from 'react';
import type { FormFailure } from './formErrors';
import styles from './panels.module.css';

/** Neutral session-bootstrap placeholder: renders while session state is
 * loading so neither guest-only nor protected content can flash. */
export function SessionPending() {
  return (
    <p className={styles.pending} role="status">
      Checking your session…
    </p>
  );
}

/** Unexpected session-bootstrap failure (never the expected anonymous
 * 401): distinct from anonymous state and retryable without resubmitting
 * anything sensitive. */
export function BootstrapErrorPanel({ retry }: { retry: () => void }) {
  return (
    <div className={styles.errorPanel} role="alert">
      <h1>We could not check your session</h1>
      <p>Something went wrong while contacting the server.</p>
      <button type="button" className={styles.panelButton} onClick={retry}>
        Try again
      </button>
    </div>
  );
}

/** Focused error summary: receives focus when a submission fails so the
 * failure is announced and reachable by keyboard. Focus keys off the
 * failure object's identity — every failed submission produces a fresh
 * object — so a repeated failure with the identical visible message is
 * still re-focused and re-announced. */
export function ErrorSummary({ failure }: { failure: FormFailure }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [failure]);
  return (
    <div ref={ref} tabIndex={-1} role="alert" className={styles.errorSummary}>
      {failure.summary}
    </div>
  );
}

/** Announced success block for terminal flow states. */
export function SuccessPanel({
  heading,
  children,
}: {
  heading: string;
  children: ReactNode;
}) {
  return (
    <div role="status" className={styles.successPanel}>
      <h2>{heading}</h2>
      {children}
    </div>
  );
}
