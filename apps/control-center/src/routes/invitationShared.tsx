import type { InvitationPreviewResponse } from '@restaurant-engine/api-client';
import styles from './authForms.module.css';

/**
 * Paste-only token entry (ADR-015): the token exists solely in controlled
 * component state. Browser assistance is disabled so the value is never
 * recorded by autofill, spellcheck, or autocorrect services.
 */
export function TokenField({
  id,
  label,
  value,
  onChange,
  error,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  const errorId = id + '-error';
  return (
    <div className={styles.field}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        name="token"
        type="text"
        autoComplete="off"
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="off"
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? errorId : undefined}
      />
      {error !== undefined && (
        <p id={errorId} className={styles.fieldError}>
          {error}
        </p>
      )}
    </div>
  );
}

/** The approved preview fields — and nothing else (never a full email). */
export function InvitationPreviewCard({
  preview,
}: {
  preview: InvitationPreviewResponse;
}) {
  return (
    <dl className={styles.preview}>
      <dt>Business</dt>
      <dd>{preview.business_name}</dd>
      <dt>Role</dt>
      <dd>{preview.role}</dd>
      <dt>Invited email</dt>
      <dd>{preview.email_hint}</dd>
    </dl>
  );
}
