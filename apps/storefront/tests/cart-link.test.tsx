// The menu page's cart link (M6C): appears only when the cart holds
// anything, counts items, and follows the storage layer's change
// announcements across island roots.

import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test } from 'vitest';

import { CartLink } from '../components/ordering/CartLink';
import { addLine, emptyCart } from '../lib/cart';
import { saveCart } from '../lib/cart-storage';

const LINE = {
  item_id: '00000000-0000-0000-0000-000000000101',
  name: 'House roast chicken',
  base_price_minor: 1250,
  quantity: 2,
  item_instructions: null,
  options: [],
};

beforeEach(() => {
  window.localStorage.clear();
});

describe('the cart link', () => {
  test('renders nothing for an empty cart', () => {
    render(<CartLink />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  test('counts items and links to checkout', () => {
    saveCart(addLine(emptyCart(), LINE).cart);
    render(<CartLink />);
    const link = screen.getByRole('link', { name: /view order \(2\)/i });
    expect(link).toHaveAttribute('href', '/order');
  });

  test('follows cart changes announced by other islands', () => {
    render(<CartLink />);
    expect(screen.queryByRole('link')).toBeNull();
    act(() => {
      saveCart(addLine(emptyCart(), LINE).cart);
    });
    expect(
      screen.getByRole('link', { name: /view order \(2\)/i }),
    ).toBeInTheDocument();
  });
});
