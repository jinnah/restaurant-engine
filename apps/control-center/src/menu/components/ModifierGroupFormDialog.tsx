import { useState, type FormEvent } from 'react';
import type { ModifierGroupView } from '@restaurant-engine/api-client';
import { Dialog } from '../../components/Dialog';
import { CheckboxField, FormField } from '../../components/FormField';
import type { FormFailure } from '../../components/formErrors';
import { ErrorSummary } from '../../components/StatusPanels';
import styles from '../menu.module.css';

export interface GroupFormValues {
  name: string;
  minSelect: number;
  maxSelect: number | null;
}

interface Props {
  group?: ModifierGroupView;
  pending: boolean;
  failure: FormFailure | null;
  onSubmit: (values: GroupFormValues) => void;
  onCancel: () => void;
}

/**
 * Create or edit a modifier group.
 *
 * "Required" is presentation: it sets `min_select`, because the contract has
 * no `is_required` field. "No limit" sends an explicit `null` for
 * `max_select`, which is the one genuinely nullable field on this command.
 */
export function ModifierGroupFormDialog({
  group,
  pending,
  failure,
  onSubmit,
  onCancel,
}: Props) {
  const editing = group !== undefined;
  const [name, setName] = useState(group?.name ?? '');
  const [required, setRequired] = useState((group?.min_select ?? 0) >= 1);
  const [minSelect, setMinSelect] = useState(
    group === undefined ? 1 : Math.max(group.min_select, 1),
  );
  const [unlimited, setUnlimited] = useState(
    group === undefined ? true : group.max_select === null,
  );
  const [maxSelect, setMaxSelect] = useState(group?.max_select ?? 1);
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) {
      return;
    }
    if (name.trim() === '') {
      setLocalError('Enter a name for this group.');
      return;
    }
    const min = required ? minSelect : 0;
    const max = unlimited ? null : maxSelect;
    if (max !== null && min > max) {
      setLocalError('The minimum cannot be more than the maximum.');
      return;
    }
    setLocalError(null);
    onSubmit({ name: name.trim(), minSelect: min, maxSelect: max });
  }

  return (
    <Dialog
      title={editing ? `Edit ${group.name}` : 'Add an option group'}
      pending={pending}
      onCancel={onCancel}
    >
      {failure !== null && localError === null && (
        <ErrorSummary failure={failure} />
      )}
      {localError !== null && (
        <p role="alert" className={styles.fieldErrorText}>
          {localError}
        </p>
      )}
      <form noValidate onSubmit={submit}>
        <FormField
          id="group-name"
          label="Group name"
          hint="What the customer sees above the choices, such as “Choose a side”."
          value={name}
          autoComplete="off"
          maxLength={120}
          error={failure?.fields['name']}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />

        <CheckboxField
          id="group-required"
          label="The customer must choose from this group"
          hint="Leave this off for extras a customer can skip."
          checked={required}
          onChange={(event) => {
            setRequired(event.target.checked);
          }}
        />

        {required && (
          <FormField
            id="group-min"
            label="Minimum choices"
            type="number"
            min={1}
            max={30}
            value={minSelect}
            onChange={(event) => {
              setMinSelect(Number(event.target.value));
            }}
          />
        )}

        <CheckboxField
          id="group-unlimited"
          label="No maximum"
          hint="The customer can pick as many as they like."
          checked={unlimited}
          onChange={(event) => {
            setUnlimited(event.target.checked);
          }}
        />

        {!unlimited && (
          <FormField
            id="group-max"
            label="Maximum choices"
            type="number"
            min={1}
            max={30}
            value={maxSelect}
            onChange={(event) => {
              setMaxSelect(Number(event.target.value));
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
            {pending ? 'Saving…' : editing ? 'Save group' : 'Add group'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
