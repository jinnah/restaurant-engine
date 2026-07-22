import { useState, type FormEvent } from 'react';
import type { CategorySummary } from '@restaurant-engine/api-client';
import { asApiFailure } from '../../api/failure';
import { Dialog } from '../../components/Dialog';
import {
  CheckboxField,
  FormField,
  TextAreaField,
} from '../../components/FormField';
import { mapFailure, type FormFailure } from '../../components/formErrors';
import { ErrorSummary } from '../../components/StatusPanels';
import styles from '../menu.module.css';

const MAX_NAME = 120;
const MAX_DESCRIPTION = 500;

export interface CategoryFormValues {
  name: string;
  description: string;
  isVisible: boolean;
}

interface CategoryFormDialogProps {
  /** Absent for a create; present for an edit. */
  category?: CategorySummary;
  pending: boolean;
  failure: FormFailure | null;
  onSubmit: (values: CategoryFormValues) => void;
  onCancel: () => void;
}

/**
 * Create or rename a category.
 *
 * Client validation covers shape only — required, trimmed, length — while
 * the server owns the truth: it normalizes the name (trim, collapse runs,
 * NFC) and enforces case-insensitive uniqueness with a database index, so
 * the response is always rendered rather than the typed value (ADR-017 R6).
 *
 * Visibility appears only when editing: a new category is created visible
 * and the create contract carries no such field, so offering the control
 * would be offering something that does nothing.
 */
export function CategoryFormDialog({
  category,
  pending,
  failure,
  onSubmit,
  onCancel,
}: CategoryFormDialogProps) {
  const editing = category !== undefined;
  const [name, setName] = useState(category?.name ?? '');
  const [description, setDescription] = useState(category?.description ?? '');
  const [isVisible, setIsVisible] = useState(category?.is_visible ?? true);
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) {
      return;
    }
    const trimmed = name.trim();
    if (trimmed === '') {
      setLocalError('Enter a name for this category.');
      return;
    }
    if (trimmed.length > MAX_NAME) {
      setLocalError(`Use at most ${String(MAX_NAME)} characters.`);
      return;
    }
    setLocalError(null);
    onSubmit({ name: trimmed, description, isVisible });
  }

  const nameError = localError ?? failure?.fields['name'];

  return (
    <Dialog
      title={editing ? `Edit ${category.name}` : 'Add a category'}
      pending={pending}
      onCancel={onCancel}
    >
      {failure !== null && localError === null && (
        <ErrorSummary failure={failure} />
      )}
      <form noValidate onSubmit={submit}>
        <FormField
          id="category-name"
          name="name"
          label="Name"
          hint="A section of your menu, such as Starters or Biryani."
          value={name}
          maxLength={MAX_NAME}
          autoComplete="off"
          error={nameError}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        <TextAreaField
          id="category-description"
          name="description"
          label="Description (optional)"
          value={description}
          maxLength={MAX_DESCRIPTION}
          error={failure?.fields['description']}
          onChange={(event) => {
            setDescription(event.target.value);
          }}
        />
        {editing && (
          <CheckboxField
            id="category-visible"
            label="Visible on the storefront"
            hint="Hidden categories and everything in them stay off your public menu."
            checked={isVisible}
            onChange={(event) => {
              setIsVisible(event.target.checked);
            }}
          />
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
          <button type="submit" className={styles.submit} disabled={pending}>
            {pending ? 'Saving…' : editing ? 'Save changes' : 'Add category'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

/** Map a failed category mutation onto form errors. */
export function categoryFailure(error: unknown, fallback: string): FormFailure {
  return mapFailure(asApiFailure(error), fallback);
}
