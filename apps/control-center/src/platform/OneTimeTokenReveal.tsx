import { useState, type ReactNode } from 'react';
import styles from './platform.module.css';

interface OneTimeTokenRevealProps {
  /** The raw single-use token from the immediate mutation response. */
  token: string;
  heading: string;
  /** Context the operator needs to deliver the token out of band. */
  children: ReactNode;
  onDismiss: () => void;
}

/**
 * Ephemeral reveal for a single-use credential (ADR-014/016): the token
 * exists only in the owning page's transient state, is rendered exactly
 * once from the issuance response, and is never refetched, persisted,
 * logged, or placed in a URL. The owner clears its state on dismiss,
 * on a new issuance attempt, and on unmount/navigation.
 */
export function OneTimeTokenReveal({
  token,
  heading,
  children,
  onDismiss,
}: OneTimeTokenRevealProps) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div role="status" className={styles.reveal}>
      <h3>{heading}</h3>
      {children}
      <p className={styles.revealWarning}>
        This token is shown once and cannot be retrieved again. Deliver it
        directly to the recipient over a channel you trust.
      </p>
      <p>
        <code className={styles.token}>{token}</code>
      </p>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void copy();
          }}
        >
          {copied ? 'Copied' : 'Copy token'}
        </button>
        <button type="button" className={styles.secondary} onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
