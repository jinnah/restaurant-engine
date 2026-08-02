'use client';

// The per-item ordering affordance (M6C, ADR-026): rendered by the menu
// page only for orderable items on an ordering-enabled storefront — the
// server decides both facts, so this island never gates anything itself.
// Confirming the picker persists the composed line to the cart.

import { useState } from 'react';

import type { PublicMenuItem } from '@restaurant-engine/api-client';

import { addLine, type CartLine } from '../../lib/cart';
import { loadCart, saveCart } from '../../lib/cart-storage';
import { ModifierPickerDialog } from './ModifierPickerDialog';
import styles from './ordering.module.css';

export function AddToCartButton({
  item,
  currency,
}: {
  item: PublicMenuItem;
  currency: string;
}) {
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
