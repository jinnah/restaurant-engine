import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import styles from './platform.module.css';

interface ConfirmDialogProps {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  /** Style the confirm action as destructive. */
  danger?: boolean;
  /**
   * Typed confirmation: the confirm action stays disabled until this
   * exact text is entered (blueprint §11.4 for terminal actions).
   */
  requireText?: string;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Accessible confirmation dialog: focus moves into the dialog on open,
 * Tab cycles within it, Escape cancels (unless a submission is in
 * flight), and focus returns to the previously focused trigger on
 * close. The confirm action disables while pending, so a consequential
 * command cannot be submitted twice.
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
  const dialogRef = useRef<HTMLDivElement>(null);
  const [typed, setTyped] = useState('');

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    dialogRef.current?.focus();
    return () => {
      previous?.focus();
    };
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape' && !pending) {
      event.stopPropagation();
      onCancel();
      return;
    }
    if (event.key === 'Tab' && dialogRef.current !== null) {
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input',
        ),
      );
      if (focusable.length === 0) {
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  }

  const confirmDisabled =
    pending || (requireText !== undefined && typed !== requireText);
  const confirmTextId = 'confirm-dialog-text';

  return (
    <div className={styles.overlay}>
      {/* The WAI-ARIA dialog pattern handles Escape and the Tab focus
          trap on the dialog container itself; the rule cannot see that
          role="dialog" makes this the correct interactive owner. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className={styles.dialog}
      >
        <h2 id="confirm-dialog-title">{title}</h2>
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
      </div>
    </div>
  );
}
