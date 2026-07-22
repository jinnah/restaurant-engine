import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react';
import styles from './controls.module.css';

interface DialogProps {
  /** Rendered as the dialog's accessible name. */
  title: string;
  children: ReactNode;
  /**
   * While true, Escape and the backdrop are inert: a consequential request
   * is in flight and dismissing would strand it (the upload and lifecycle
   * flows both rely on this).
   */
  pending?: boolean;
  onCancel: () => void;
  /** Extra class for the dialog surface (wider editors, for example). */
  className?: string;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The modal shell every dialog in the app shares (M3E): focus moves in on
 * open, Tab cycles inside, Escape cancels unless a submission is in flight,
 * and focus returns to the trigger on close.
 *
 * Extracted from the M2F ConfirmDialog when the menu forms became a second
 * real consumer, so the focus contract has exactly one implementation.
 * Because a dialog owns keyboard focus while it is open, nothing outside it
 * may render an interactive affordance above it — see NotificationProvider.
 */
export function Dialog({
  title,
  children,
  pending = false,
  onCancel,
  className,
}: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    dialogRef.current?.focus();
    return () => {
      // Focus return is what makes a dialog survivable by keyboard: the user
      // lands back on the control they opened it from, not at the page top.
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
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
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

  return (
    <div className={styles.overlay}>
      {/* The WAI-ARIA dialog pattern handles Escape and the Tab focus trap on
          the dialog container itself; the rule cannot see that role="dialog"
          makes this the correct interactive owner. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className={
          className === undefined
            ? styles.dialog
            : `${styles.dialog} ${className}`
        }
      >
        <h2 id="dialog-title">{title}</h2>
        {children}
      </div>
    </div>
  );
}
