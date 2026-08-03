'use client';

// The per-item ordering affordance (M6C, ADR-026): rendered by the menu
// page only for orderable items on an ordering-enabled storefront — the
// server decides both facts, so this island never gates anything itself.
// Confirming the picker persists the composed line to the cart.

import { useState, useSyncExternalStore } from 'react';

import type { PublicMenuItem } from '@restaurant-engine/api-client';

import { addLine, type CartLine } from '../../lib/cart';
import { loadCart, saveCart } from '../../lib/cart-storage';
import { ModifierPickerDialog } from './ModifierPickerDialog';
import styles from './ordering.module.css';

const subscribeNever = () => () => {};

/**
 * True once React owns the DOM. The server document renders this button
 * disabled: a control whose click handler has not attached yet is a lie
 * to a fast finger on a slow connection (and to a browser driver), so
 * the affordance is honest about readiness instead of silently inert —
 * found by the M6D journey clicking before hydration completed.
 */
function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false,
  );
}

export function AddToCartButton({
  item,
  currency,
}: {
  item: PublicMenuItem;
  currency: string;
}) {
  const hydrated = useHydrated();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const handleAdd = (line: CartLine): void => {
    const result = addLine(loadCart(), line);
    if (result.ok) {
      saveCart(result.cart);
      setNote('Added');
    } else {
      setNote('Your order is full — review it before adding more.');
    }
  };

  return (
    <div>
      <button
        type="button"
        className={styles.addButton}
        disabled={!hydrated}
        onClick={() => {
          setNote(null);
          setOpen(true);
        }}
      >
        Add to order
      </button>
      {note === null ? null : (
        <span role="status" className={styles.addedNote}>
          {note}
        </span>
      )}
      <ModifierPickerDialog
        item={item}
        currency={currency}
        open={open}
        onClose={() => {
          setOpen(false);
        }}
        onAdd={handleAdd}
      />
    </div>
  );
}
