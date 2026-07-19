import type { ComponentPropsWithoutRef } from 'react';
import styles from './platform.module.css';

interface FormFieldProps extends ComponentPropsWithoutRef<'input'> {
  id: string;
  label: string;
  /** Inline field error from the mapped ADR-008 envelope. */
  error?: string;
}

/** Labeled input with accessible error association (M2E form pattern). */
export function FormField({ id, label, error, ...inputProps }: FormFieldProps) {
  const errorId = `${id}-error`;
  return (
    <div className={styles.field}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? errorId : undefined}
        {...inputProps}
      />
      {error !== undefined && (
        <p id={errorId} className={styles.fieldError}>
          {error}
        </p>
      )}
    </div>
  );
}
