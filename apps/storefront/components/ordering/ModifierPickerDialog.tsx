'use client';

// The modifier picker (M6C, ADR-026): a native <dialog> the menu page
// opens per item. Selection rules render and enforce locally for the
// experience — min/max per group, single-choice groups behave like
// radios — while the server stays authoritative at placement (the M6A
// pricing core revalidates everything). The running total is a display
// hint composed from the projection's own prices.

import { useEffect, useMemo, useRef, useState } from 'react';

import type {
  PublicMenuItem,
  PublicModifierGroup,
} from '@restaurant-engine/api-client';
import { formatMinorUnits } from '@restaurant-engine/storefront-renderer/money';

import {
  MAX_LINE_QUANTITY,
  type CartLine,
  type CartOption,
} from '../../lib/cart';
import styles from './ordering.module.css';

const MAX_ITEM_INSTRUCTIONS = 200;

function groupRule(group: PublicModifierGroup): string {
  const { min_select: min, max_select: max } = group;
  if (min === 1 && max === 1) return 'Choose one';
  const parts: string[] = [];
  if (min > 0) parts.push(`at least ${String(min)}`);
  if (max !== null) parts.push(`up to ${String(max)}`);
  return parts.length === 0 ? 'Optional' : `Choose ${parts.join(', ')}`;
}

function groupSatisfied(
  group: PublicModifierGroup,
  selected: Set<string>,
): boolean {
  let count = 0;
  for (const option of group.options) {
    if (selected.has(option.id)) count += 1;
  }
  return (
    count >= group.min_select &&
    (group.max_select === null || count <= group.max_select)
  );
}

export function ModifierPickerDialog({
  item,
  currency,
  open,
  onClose,
  onAdd,
}: {
  item: PublicMenuItem;
  currency: string;
  open: boolean;
  onClose: () => void;
  onAdd: (line: CartLine) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [quantity, setQuantity] = useState(1);
  const [instructions, setInstructions] = useState('');

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (open && !dialog.open) {
      setSelected(new Set());
      setQuantity(1);
      setInstructions('');
      // Progressive enhancement: `showModal` gives the native modal
      // behavior (backdrop, focus trap, Escape); an environment without
      // it (older browsers, jsdom) still opens the dialog element.
      if (typeof dialog.showModal === 'function') {
        dialog.showModal();
      } else {
        dialog.open = true;
      }
    } else if (!open && dialog.open) {
      if (typeof dialog.close === 'function') {
        dialog.close();
      } else {
        dialog.open = false;
      }
    }
  }, [open]);

  const toggleOption = (group: PublicModifierGroup, optionId: string): void => {
    setSelected((current) => {
      const next = new Set(current);
      const single = group.min_select === 1 && group.max_select === 1;
      if (single) {
        for (const option of group.options) next.delete(option.id);
        next.add(optionId);
        return next;
      }
      if (next.has(optionId)) {
        next.delete(optionId);
        return next;
      }
      if (group.max_select !== null) {
        const count = group.options.filter((option) =>
          next.has(option.id),
        ).length;
        if (count >= group.max_select) return current;
      }
      next.add(optionId);
      return next;
    });
  };

  const chosenOptions: CartOption[] = useMemo(
    () =>
      item.modifier_groups.flatMap((group) =>
        group.options
          .filter((option) => selected.has(option.id))
          .map((option) => ({
            group_id: group.id,
            group_name: group.name,
            option_id: option.id,
            option_name: option.name,
            price_delta_minor: option.price_delta_minor,
          })),
      ),
    [item, selected],
  );

  const unitMinor =
    item.price_minor +
    chosenOptions.reduce((sum, option) => sum + option.price_delta_minor, 0);
  const valid = item.modifier_groups.every((group) =>
    groupSatisfied(group, selected),
  );

  const confirm = (): void => {
    if (!valid) return;
    const trimmed = instructions.trim();
    onAdd({
      item_id: item.id,
      name: item.name,
      base_price_minor: item.price_minor,
      quantity,
      item_instructions: trimmed === '' ? null : trimmed,
      options: chosenOptions,
    });
    onClose();
  };

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby={`picker-heading-${item.id}`}
      onClose={onClose}
    >
      <h2 id={`picker-heading-${item.id}`} className={styles.dialogHeading}>
        {item.name}
      </h2>
      <p className={styles.dialogPrice}>
        {formatMinorUnits(item.price_minor, currency)}
      </p>
      {item.modifier_groups.map((group) => {
        const single = group.min_select === 1 && group.max_select === 1;
        return (
          <fieldset key={group.id} className={styles.group}>
            <legend className={styles.groupName}>{group.name}</legend>
            <span className={styles.groupRule}>{groupRule(group)}</span>
            {group.options.map((option) => (
              <label key={option.id} className={styles.optionRow}>
                <input
                  type={single ? 'radio' : 'checkbox'}
                  name={`group-${group.id}`}
                  checked={selected.has(option.id)}
                  onChange={() => {
                    toggleOption(group, option.id);
                  }}
                />
                <span>{option.name}</span>
                {option.price_delta_minor === 0 ? null : (
                  <span className={styles.optionDelta}>
                    +{formatMinorUnits(option.price_delta_minor, currency)}
                  </span>
                )}
              </label>
            ))}
          </fieldset>
        );
      })}
      <div className={styles.quantityRow}>
        <button
          type="button"
          className={styles.quantityButton}
          aria-label="Decrease quantity"
          disabled={quantity <= 1}
          onClick={() => {
            setQuantity((q) => Math.max(1, q - 1));
          }}
        >
          −
        </button>
        <span aria-live="polite" className={styles.quantityValue}>
          {quantity}
        </span>
        <button
          type="button"
          className={styles.quantityButton}
          aria-label="Increase quantity"
          disabled={quantity >= MAX_LINE_QUANTITY}
          onClick={() => {
            setQuantity((q) => Math.min(MAX_LINE_QUANTITY, q + 1));
          }}
        >
          +
        </button>
      </div>
      <label className={styles.fieldLabel} htmlFor={`picker-notes-${item.id}`}>
        Special requests (optional)
      </label>
      <textarea
        id={`picker-notes-${item.id}`}
        className={styles.textArea}
        maxLength={MAX_ITEM_INSTRUCTIONS}
        value={instructions}
        onChange={(event) => {
          setInstructions(event.target.value);
        }}
      />
      <div className={styles.dialogActions}>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={onClose}
        >
          Cancel
        </button>
        <button
          type="button"
          className={styles.primaryButton}
          disabled={!valid}
          onClick={confirm}
        >
          Add {String(quantity)} ·{' '}
          {formatMinorUnits(unitMinor * quantity, currency)}
        </button>
      </div>
    </dialog>
  );
}
