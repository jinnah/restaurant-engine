import type { ComponentPropsWithRef, ReactNode } from 'react';
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

/**
 * `ref` is accepted as an ordinary prop (React 19) rather than through
 * forwardRef, because React Hook Form's `register()` returns one in its prop
 * bundle and the whole bundle is spread onto these components.
 */
interface FormFieldProps extends ComponentPropsWithRef<'input'> {
  id: string;
  label: ReactNode;
  hint?: string;
  /** Inline field error from the Zod schema or the mapped ADR-008 envelope. */
  error?: string;
  /**
   * A short decorative symbol inside the field box — a currency symbol for a
   * price, for example. Purely visual (the label already carries the meaning),
   * so it is hidden from assistive technology. Typed as `string` to stay
   * compatible with the global HTML `prefix` attribute this interface extends.
   */
  prefix?: string;
}

/** Labelled input with accessible error association (the M2E form pattern). */
export function FormField({
  id,
  label,
  hint,
  error,
  prefix,
  ...inputProps
}: FormFieldProps) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error}>
      {(describedBy) =>
        prefix === undefined ? (
          <input
            id={id}
            aria-invalid={error !== undefined}
            aria-describedby={describedBy}
            {...inputProps}
          />
        ) : (
          <div
            className={styles.affix}
            data-invalid={error !== undefined ? 'true' : undefined}
          >
            <span className={styles.affixSymbol} aria-hidden="true">
              {prefix}
            </span>
            <input
              id={id}
              aria-invalid={error !== undefined}
              aria-describedby={describedBy}
              {...inputProps}
            />
          </div>
        )
      }
    </FieldShell>
  );
}

interface TextAreaFieldProps extends ComponentPropsWithRef<'textarea'> {
  id: string;
  label: ReactNode;
  hint?: string;
  error?: string;
}

/** Labelled textarea sharing the input field's error semantics. */
export function TextAreaField({
  id,
  label,
  hint,
  error,
  ...props
}: TextAreaFieldProps) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error}>
      {(describedBy) => (
        <textarea
          id={id}
          aria-invalid={error !== undefined}
          aria-describedby={describedBy}
          {...props}
        />
      )}
    </FieldShell>
  );
}

interface SelectFieldProps extends ComponentPropsWithRef<'select'> {
  id: string;
  label: ReactNode;
  hint?: string;
  error?: string;
  children: ReactNode;
}

/** Labelled select sharing the input field's error semantics. */
export function SelectField({
  id,
  label,
  hint,
  error,
  children,
  ...props
}: SelectFieldProps) {
  return (
    <FieldShell id={id} label={label} hint={hint} error={error}>
      {(describedBy) => (
        <select
          id={id}
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

interface CheckboxFieldProps extends ComponentPropsWithRef<'input'> {
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
