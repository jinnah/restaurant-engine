// @vitest-environment node

// The pure cart value (M6C, ADR-026 D13): versioned schema, merge and
// bound behavior, display totals, and the placement payload mapping.
// Everything here runs without a browser — persistence has its own test.

import { describe, expect, test } from 'vitest';

import {
  addLine,
  cartItemCount,
  cartTotalMinor,
  emptyCart,
  lineTotalMinor,
  MAX_CART_LINES,
  MAX_LINE_QUANTITY,
  parseCart,
  removeLine,
  serializeCart,
  setLineQuantity,
  toPlacementLines,
  type CartLine,
} from '../lib/cart';

function line(overrides: Partial<CartLine> = {}): CartLine {
  return {
    item_id: '00000000-0000-0000-0000-000000000101',
    name: 'House roast chicken',
    base_price_minor: 1250,
    quantity: 1,
    item_instructions: null,
    options: [],
    ...overrides,
  };
}

const OPTION = {
  group_id: 'g1',
  group_name: 'Spice level',
  option_id: 'o1',
  option_name: 'Hot',
  price_delta_minor: 50,
};

describe('cart arithmetic', () => {
  test('line total is (base + deltas) × quantity', () => {
    expect(lineTotalMinor(line({ quantity: 3, options: [OPTION] }))).toBe(
      (1250 + 50) * 3,
    );
  });

  test('cart total and item count sum every line', () => {
    let cart = emptyCart();
    cart = addLine(cart, line({ quantity: 2 })).cart;
    cart = addLine(
      cart,
      line({ item_id: 'other', options: [OPTION], quantity: 1 }),
    ).cart;
    expect(cartTotalMinor(cart)).toBe(2500 + 1300);
    expect(cartItemCount(cart)).toBe(3);
  });
});

describe('adding lines', () => {
  test('an identical choice merges quantities', () => {
    let cart = emptyCart();
    cart = addLine(cart, line({ quantity: 2, options: [OPTION] })).cart;
    cart = addLine(cart, line({ quantity: 3, options: [OPTION] })).cart;
    expect(cart.lines).toHaveLength(1);
    expect(cart.lines[0]?.quantity).toBe(5);
  });

  test('merged quantity caps at the contract bound', () => {
    let cart = emptyCart();
    cart = addLine(cart, line({ quantity: 49 })).cart;
    cart = addLine(cart, line({ quantity: 5 })).cart;
    expect(cart.lines[0]?.quantity).toBe(MAX_LINE_QUANTITY);
  });

  test('different options are a new line, not a merge', () => {
    let cart = emptyCart();
    cart = addLine(cart, line()).cart;
    cart = addLine(cart, line({ options: [OPTION] })).cart;
    expect(cart.lines).toHaveLength(2);
  });

  test('different instructions are a new line, not a merge', () => {
    let cart = emptyCart();
    cart = addLine(cart, line()).cart;
    cart = addLine(cart, line({ item_instructions: 'no onions' })).cart;
    expect(cart.lines).toHaveLength(2);
  });

  test('the line cap refuses with the cart unchanged', () => {
    let cart = emptyCart();
    for (let i = 0; i < MAX_CART_LINES; i += 1) {
      cart = addLine(cart, line({ item_id: `item-${String(i)}` })).cart;
    }
    const result = addLine(cart, line({ item_id: 'one-too-many' }));
    expect(result.ok).toBe(false);
    expect(result.cart.lines).toHaveLength(MAX_CART_LINES);
  });
});

describe('editing lines', () => {
  test('remove drops exactly the indexed line', () => {
    let cart = emptyCart();
    cart = addLine(cart, line({ item_id: 'a' })).cart;
    cart = addLine(cart, line({ item_id: 'b' })).cart;
    expect(removeLine(cart, 0).lines.map((l) => l.item_id)).toEqual(['b']);
  });

  test('quantity edits stay inside the contract bounds', () => {
    let cart = emptyCart();
    cart = addLine(cart, line()).cart;
    expect(setLineQuantity(cart, 0, 7).lines[0]?.quantity).toBe(7);
    expect(setLineQuantity(cart, 0, 0).lines[0]?.quantity).toBe(1);
    expect(
      setLineQuantity(cart, 0, MAX_LINE_QUANTITY + 1).lines[0]?.quantity,
    ).toBe(1);
    expect(setLineQuantity(cart, 0, 1.5).lines[0]?.quantity).toBe(1);
  });
});

describe('the placement payload', () => {
  test('carries references and quantities, never prices', () => {
    let cart = emptyCart();
    cart = addLine(
      cart,
      line({ quantity: 2, options: [OPTION], item_instructions: 'well done' }),
    ).cart;
    expect(toPlacementLines(cart)).toEqual([
      {
        item_id: '00000000-0000-0000-0000-000000000101',
        quantity: 2,
        option_ids: ['o1'],
        item_instructions: 'well done',
      },
    ]);
  });
});

describe('the versioned persisted schema', () => {
  test('round-trips the current schema exactly', () => {
    let cart = emptyCart();
    cart = addLine(cart, line({ options: [OPTION] })).cart;
    expect(parseCart(serializeCart(cart))).toEqual(cart);
  });

  test.each([
    ['nothing stored', null],
    ['malformed JSON', '{not json'],
    ['a non-object', '"cart"'],
    ['an unknown schema version', '{"schema_version":2,"lines":[]}'],
    ['a missing version', '{"lines":[]}'],
    [
      'structurally wrong lines',
      '{"schema_version":1,"lines":[{"item_id":1}]}',
    ],
    [
      'an out-of-bounds quantity',
      `{"schema_version":1,"lines":[${JSON.stringify({
        ...line(),
        quantity: 51,
      })}]}`,
    ],
  ])('%s drops the cart cleanly to empty', (_label, raw) => {
    expect(parseCart(raw)).toEqual(emptyCart());
  });
});
