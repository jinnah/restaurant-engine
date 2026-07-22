import type {
  ComponentPropsWithoutRef,
  ReactNode,
  Ref,
  TextareaHTMLAttributes,
} from 'react';
import styles from './controls.module.css';

interface FieldShellProps {
  id: string;
  label: ReactNode;
  hint?: string;
  error?: string;
  children: (describedBy: string | undefined) => ReactNode;
}

/**
 * The label/hint/error scaffolding every field shares. `aria-describedby`
 * carries the hint and the error together, so a screen-reader user hears the
 * guidance and the failure rather than one replacing the other.
 */
function FieldShell({ id, label, hint, error, children }: FieldShellProps) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy =
    [hint !== undefined ? hintId : null, error !== undefined ? errorId : null]
      .filter((value): value is string => value !== null)
      .join(' ') || undefined;

  return (
    <div className={styles.field}>
      <label htmlFor={id}>{label}</label>
      {children(describedBy)}
      {hint !== undefined && (
        <p id={hintId} className={styles.fieldHint}>
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={errorId} className={styles.fieldError}>
          {error}
        </p>
      )}
    </div>
  );
}

interface FormFieldProps extends ComponentPropsWithoutRef<'input'> {
  id: string;
  label: ReactNode;
  hint?: string;
  /** Inline field error from the mapped ADR-008 envelope or the Zod schema. */
  error?: string;
  inputRef?: Ref<HTMLInputElement>;
}

/** Labelled input with accessible error association (the M2E form pattern). */
export function FormField({
  id,
  label,
  hint,
  error,
  inputRef,
  ...inputProps
}: FormFieldProps) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error}>
      {(describedBy) => (
        <input
          id={id}
          ref={inputRef}
          aria-invalid={error !== undefined}
          aria-describedby={describedBy}
          {...inputProps}
        />
      )}
    </FieldShell>
  );
}

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  id: string;
  label: ReactNode;
  hint?: string;
  error?: string;
  textareaRef?: Ref<HTMLTextAreaElement>;
}

/** Labelled textarea sharing the input field's error semantics. */
export function TextAreaField({
  id,
  label,
  hint,
  error,
  textareaRef,
  ...props
}: TextAreaFieldProps) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error}>
      {(describedBy) => (
        <textarea
          id={id}
          ref={textareaRef}
          aria-invalid={error !== undefined}
          aria-describedby={describedBy}
          {...props}
        />
      )}
    </FieldShell>
  );
}

interface SelectFieldProps extends ComponentPropsWithoutRef<'select'> {
  id: string;
  label: ReactNode;
  hint?: string;
  error?: string;
  children: ReactNode;
  selectRef?: Ref<HTMLSelectElement>;
}

/** Labelled select sharing the input field's error semantics. */
export function SelectField({
  id,
  label,
  hint,
  error,
  children,
  selectRef,
  ...props
}: SelectFieldProps) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error}>
      {(describedBy) => (
        <select
          id={id}
          ref={selectRef}
          aria-invalid={error !== undefined}
          aria-describedby={describedBy}
          {...props}
        >
          {children}
        </select>
      )}
    </FieldShell>
  );
}

interface CheckboxFieldProps extends ComponentPropsWithoutRef<'input'> {
  id: string;
  label: ReactNode;
  hint?: string;
}

/**
 * Labelled checkbox. The 44px target is the whole row, not the box the
 * browser draws, so the label and control share one hit area.
 */
export function CheckboxField({
  id,
  label,
  hint,
  ...props
}: CheckboxFieldProps) {
  const hintId = `${id}-hint`;
  return (
    <div className={styles.check}>
      <input
        id={id}
        type="checkbox"
        aria-describedby={hint !== undefined ? hintId : undefined}
        {...props}
      />
      <div>
        <label htmlFor={id}>{label}</label>
        {hint !== undefined && (
          <p id={hintId} className={styles.fieldHint}>
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}
