// The add-to-order affordance and the modifier picker (M6C, ADR-026):
// local enforcement of the projection's selection rules — single-choice
// groups behave like radios, max caps hold, the confirm is disabled
// until every group is satisfied — and the confirmed line lands in the
// stored cart. The server stays authoritative; what is under test is
// the honest local experience.

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test } from 'vitest';

import { AddToCartButton } from '../components/ordering/AddToCartButton';
import { loadCart } from '../lib/cart-storage';
import { menuItemFixture } from '@restaurant-engine/storefront-renderer/fixtures';
import type { PublicMenuItem } from '@restaurant-engine/api-client';

function itemWithGroups(): PublicMenuItem {
  return menuItemFixture({
    modifier_groups: [
      {
        id: 'g-size',
        name: 'Size',
        min_select: 1,
        max_select: 1,
        options: [
          { id: 'o-half', name: 'Half', price_delta_minor: 0 },
          { id: 'o-full', name: 'Full', price_delta_minor: 400 },
        ],
      },
      {
        id: 'g-extras',
        name: 'Extras',
        min_select: 0,
        max_select: 2,
        options: [
          { id: 'o-naan', name: 'Naan', price_delta_minor: 250 },
          { id: 'o-raita', name: 'Raita', price_delta_minor: 150 },
          { id: 'o-salad', name: 'Salad', price_delta_minor: 200 },
        ],
      },
    ],
  });
}

function openPicker(item = itemWithGroups()): void {
  render(<AddToCartButton item={item} currency="USD" />);
  fireEvent.click(screen.getByRole('button', { name: /add to order/i }));
}

function confirmButton(): HTMLElement {
  return screen.getByRole('button', { name: /^Add \d/ });
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('the modifier picker', () => {
  test('confirm stays disabled until every required group is satisfied', () => {
    openPicker();
    expect(confirmButton()).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: /full/i }));
    expect(confirmButton()).toBeEnabled();
  });

  test('a single-choice group replaces the selection like a radio', () => {
    openPicker();
    fireEvent.click(screen.getByRole('radio', { name: /half/i }));
    fireEvent.click(screen.getByRole('radio', { name: /full/i }));
    expect(screen.getByRole('radio', { name: /half/i })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: /full/i })).toBeChecked();
  });

  test('the max cap refuses further selections without unchecking', () => {
    openPicker();
    fireEvent.click(screen.getByRole('checkbox', { name: /naan/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /raita/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /salad/i }));
    expect(screen.getByRole('checkbox', { name: /naan/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /raita/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /salad/i })).not.toBeChecked();
  });

  test('the running total composes base, deltas, and quantity', () => {
    openPicker();
    fireEvent.click(screen.getByRole('radio', { name: /full/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /naan/i }));
    fireEvent.click(screen.getByRole('button', { name: /increase quantity/i }));
    // (1250 + 400 + 250) × 2 = 3800 minor units.
    expect(confirmButton()).toHaveTextContent('Add 2 · $38.00');
  });

  test('confirming persists the composed line to the stored cart', () => {
    openPicker();
    fireEvent.click(screen.getByRole('radio', { name: /full/i }));
    fireEvent.change(screen.getByLabelText(/special requests/i), {
      target: { value: '  extra crispy  ' },
    });
    fireEvent.click(confirmButton());
    const cart = loadCart();
    expect(cart.lines).toHaveLength(1);
    expect(cart.lines[0]).toMatchObject({
      item_id: '00000000-0000-0000-0000-000000000101',
      base_price_minor: 1250,
      quantity: 1,
      item_instructions: 'extra crispy',
      options: [
        {
          group_id: 'g-size',
          option_id: 'o-full',
          price_delta_minor: 400,
        },
      ],
    });
    expect(screen.getByRole('status')).toHaveTextContent('Added');
  });

  test('an item without groups confirms immediately', () => {
    openPicker(menuItemFixture());
    expect(confirmButton()).toBeEnabled();
    fireEvent.click(confirmButton());
    expect(loadCart().lines).toHaveLength(1);
  });
});
