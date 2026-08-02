// Cart persistence (M6C, ADR-026 D13): localStorage round-trip, the
// clean drop of anything unrecognized, and the change announcement the
// separate island roots coordinate through.

import { beforeEach, describe, expect, test, vi } from 'vitest';

import { addLine, emptyCart } from '../lib/cart';
import {
  CART_CHANGED_EVENT,
  CART_STORAGE_KEY,
  clearStoredCart,
  loadCart,
  saveCart,
} from '../lib/cart-storage';

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

describe('cart storage', () => {
  test('saves and loads the versioned cart', () => {
    const { cart } = addLine(emptyCart(), LINE);
    saveCart(cart);
    expect(loadCart()).toEqual(cart);
  });

  test('an unknown stored version loads as an empty cart', () => {
    window.localStorage.setItem(
      CART_STORAGE_KEY,
      '{"schema_version":99,"lines":[]}',
    );
    expect(loadCart()).toEqual(emptyCart());
  });

  test('clearing removes the stored value', () => {
    saveCart(addLine(emptyCart(), LINE).cart);
    clearStoredCart();
    expect(window.localStorage.getItem(CART_STORAGE_KEY)).toBeNull();
    expect(loadCart()).toEqual(emptyCart());
  });

  test('save and clear announce the change to other islands', () => {
    const heard = vi.fn();
    window.addEventListener(CART_CHANGED_EVENT, heard);
    try {
      saveCart(emptyCart());
      clearStoredCart();
      expect(heard).toHaveBeenCalledTimes(2);
    } finally {
      window.removeEventListener(CART_CHANGED_EVENT, heard);
    }
  });
});
