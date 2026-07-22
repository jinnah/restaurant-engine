import { useState, type FormEvent } from 'react';
import type { ModifierOptionView } from '@restaurant-engine/api-client';
import { Dialog } from '../../components/Dialog';
import { CheckboxField, FormField } from '../../components/FormField';
import type { FormFailure } from '../../components/formErrors';
import { ErrorSummary } from '../../components/StatusPanels';
import {
  minorToMajorInput,
  moneyErrorMessage,
  parseMajorToMinor,
} from '../money';
import styles from '../menu.module.css';

export interface OptionFormValues {
  name: string;
  priceDeltaMinor: number;
  isAvailable: boolean;
}

interface Props {
  option?: ModifierOptionView;
  currency: string;
  pending: boolean;
  failure: FormFailure | null;
  onSubmit: (values: OptionFormValues) => void;
  onCancel: () => void;
}

/**
 * Create or edit one choice inside a group.
 *
 * The price is a surcharge, not a price: `price_delta_minor` is what this
 * choice adds to the item. Availability rides this form because options have
 * no separate availability command (ruling D3), unlike items.
 */
export function ModifierOptionFormDialog({
  option,
  currency,
  pending,
  failure,
  onSubmit,
  onCancel,
}: Props) {
  const editing = option !== undefined;
  const [name, setName] = useState(option?.name ?? '');
  const [price, setPrice] = useState(
    option === undefined
      ? minorToMajorInput(0, currency)
      : minorToMajorInput(option.price_delta_minor, currency),
  );
  const [isAvailable, setIsAvailable] = useState(option?.is_available ?? true);
  const [nameError, setNameError] = useState<string | null>(null);
  const [priceError, setPriceError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) {
      return;
    }
    let invalid = false;
    if (name.trim() === '') {
      setNameError('Enter a name for this choice.');
      invalid = true;
    } else {
      setNameError(null);
    }
    const parsed = parseMajorToMinor(price, currency);
    if (!parsed.ok) {
      setPriceError(moneyErrorMessage(parsed.error, currency));
      invalid = true;
    } else {
      setPriceError(null);
    }
    if (invalid || !parsed.ok) {
      return;
    }
    onSubmit({
      name: name.trim(),
      priceDeltaMinor: parsed.minor,
      isAvailable,
    });
  }

  return (
    <Dialog
      title={editing ? `Edit ${option.name}` : 'Add a choice'}
      pending={pending}
      onCancel={onCancel}
    >
      {failure !== null && <ErrorSummary failure={failure} />}
      <form noValidate onSubmit={submit}>
        <FormField
          id="option-name"
          label="Choice name"
          autoComplete="off"
          maxLength={120}
          value={name}
          error={nameError ?? failure?.fields['name']}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        <FormField
          id="option-price"
          label={`Extra charge (${currency})`}
          hint="What this choice adds to the item's price. Use 0 for no extra charge."
          inputMode="decimal"
          autoComplete="off"
          value={price}
          error={priceError ?? failure?.fields['price_delta_minor']}
          onChange={(event) => {
            setPrice(event.target.value);
          }}
        />
        {editing && (
          <CheckboxField
            id="option-available"
            label="Available"
            hint="Unavailable choices are hidden from customers but kept here."
            checked={isAvailable}
            onChange={(event) => {
              setIsAvailable(event.target.checked);
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
            {pending ? 'Saving…' : editing ? 'Save choice' : 'Add choice'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
