import { useState, type ReactNode } from 'react';
import { Dialog } from './Dialog';
import styles from './controls.module.css';

interface ConfirmDialogProps {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  /** Style the confirm action as destructive. */
  danger?: boolean;
  /**
   * Typed confirmation: the confirm action stays disabled until this exact
   * text is entered (blueprint §11.4 for terminal actions).
   */
  requireText?: string;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Proportionate confirmation for a consequential action. The focus contract
 * lives in Dialog; this adds the confirm/cancel pair, the optional typed
 * confirmation, and the pending lock that stops a double submission.
 *
 * Deletes in this application are hard deletes — the backend exposes no
 * restore contract — so confirmation is the only safeguard there is. Nothing
 * offers "undo", and no flow recreates a deleted record to imitate one
 * (ADR-018 ruling 12).
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  danger = false,
  requireText,
  pending,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('');
  const confirmDisabled =
    pending || (requireText !== undefined && typed !== requireText);
  const confirmTextId = 'confirm-dialog-text';

  return (
    <Dialog title={title} pending={pending} onCancel={onCancel}>
      {children}
      {requireText !== undefined && (
        <div className={styles.field}>
          <label htmlFor={confirmTextId}>
            Type <strong>{requireText}</strong> to confirm
          </label>
          <input
            id={confirmTextId}
            type="text"
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
        </div>
      )}
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.secondary}
          onClick={onCancel}
          disabled={pending}
        >
          Cancel
        </button>
        <button
          type="button"
          className={danger ? styles.danger : styles.submit}
          onClick={onConfirm}
          disabled={confirmDisabled}
        >
          {pending ? 'Working…' : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
