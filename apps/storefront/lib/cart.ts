// The guest cart (M6C, ADR-026 D13): a pure, versioned client-side value.
//
// The cart is a display-level draft — it stores the prices the visitor
// saw so the surface can render totals, but every stored amount is a
// display hint: the server reprices the whole cart authoritatively at
// placement (D8), and `expected_total_minor` exists to refuse surprises,
// never to be believed. The persisted schema carries `schema_version`;
// anything unrecognized — an unknown version, a structural mismatch, a
// parse failure — drops the cart cleanly to empty (blueprint §19: cart
// schema/versioning). Everything here is pure; persistence lives in
// `cart-storage.ts`.

export const CART_SCHEMA_VERSION = 1;

// The contract's own bounds (OrderPlace / CartLineIn pins), mirrored so
// the surface never composes a cart the server would reject on shape.
export const MAX_CART_LINES = 30;
export const MAX_LINE_QUANTITY = 50;

export interface CartOption {
  group_id: string;
  group_name: string;
  option_id: string;
  option_name: string;
  price_delta_minor: number;
}

export interface CartLine {
  item_id: string;
  name: string;
  base_price_minor: number;
  quantity: number;
  item_instructions: string | null;
  options: CartOption[];
}

export interface Cart {
  schema_version: typeof CART_SCHEMA_VERSION;
  lines: CartLine[];
}

export function emptyCart(): Cart {
  return { schema_version: CART_SCHEMA_VERSION, lines: [] };
}

function sortedOptionIds(line: CartLine): string {
  return line.options
    .map((option) => option.option_id)
    .sort()
    .join(',');
}

/** Two lines merge when they are the same choice in every respect. */
function sameChoice(a: CartLine, b: CartLine): boolean {
  return (
    a.item_id === b.item_id &&
    a.item_instructions === b.item_instructions &&
    sortedOptionIds(a) === sortedOptionIds(b)
  );
}

/**
 * Add one composed line. An identical choice merges quantities (capped
 * at the contract bound); a genuinely new choice appends. `ok: false`
 * means the cart is full (the line cap) and nothing changed.
 */
export function addLine(
  cart: Cart,
  line: CartLine,
): { cart: Cart; ok: boolean } {
  const index = cart.lines.findIndex((existing) => sameChoice(existing, line));
  if (index >= 0) {
    const merged = cart.lines.map((existing, i) =>
      i === index
        ? {
            ...existing,
            quantity: Math.min(
              existing.quantity + line.quantity,
              MAX_LINE_QUANTITY,
            ),
          }
        : existing,
    );
    return { cart: { ...cart, lines: merged }, ok: true };
  }
  if (cart.lines.length >= MAX_CART_LINES) {
    return { cart, ok: false };
  }
  return { cart: { ...cart, lines: [...cart.lines, line] }, ok: true };
}

export function removeLine(cart: Cart, index: number): Cart {
  return { ...cart, lines: cart.lines.filter((_, i) => i !== index) };
}

export function setLineQuantity(
  cart: Cart,
  index: number,
  quantity: number,
): Cart {
  if (
    !Number.isSafeInteger(quantity) ||
    quantity < 1 ||
    quantity > MAX_LINE_QUANTITY
  ) {
    return cart;
  }
  return {
    ...cart,
    lines: cart.lines.map((line, i) =>
      i === index ? { ...line, quantity } : line,
    ),
  };
}

/** The displayed line total: (base + option deltas) × quantity. */
export function lineTotalMinor(line: CartLine): number {
  const unit =
    line.base_price_minor +
    line.options.reduce((sum, option) => sum + option.price_delta_minor, 0);
  return unit * line.quantity;
}

/** The displayed cart total — the value submitted as `expected_total_minor`. */
export function cartTotalMinor(cart: Cart): number {
  return cart.lines.reduce((sum, line) => sum + lineTotalMinor(line), 0);
}

export function cartItemCount(cart: Cart): number {
  return cart.lines.reduce((sum, line) => sum + line.quantity, 0);
}

/** The placement payload's lines: references and quantities, never prices. */
export function toPlacementLines(cart: Cart): Array<{
  item_id: string;
  quantity: number;
  option_ids: string[];
  item_instructions: string | null;
}> {
  return cart.lines.map((line) => ({
    item_id: line.item_id,
    quantity: line.quantity,
    option_ids: line.options.map((option) => option.option_id),
    item_instructions: line.item_instructions,
  }));
}

function isCartOption(value: unknown): value is CartOption {
  if (typeof value !== 'object' || value === null) return false;
  const option = value as Record<string, unknown>;
  return (
    typeof option['group_id'] === 'string' &&
    typeof option['group_name'] === 'string' &&
    typeof option['option_id'] === 'string' &&
    typeof option['option_name'] === 'string' &&
    typeof option['price_delta_minor'] === 'number' &&
    Number.isSafeInteger(option['price_delta_minor'])
  );
}

function isCartLine(value: unknown): value is CartLine {
  if (typeof value !== 'object' || value === null) return false;
  const line = value as Record<string, unknown>;
  return (
    typeof line['item_id'] === 'string' &&
    typeof line['name'] === 'string' &&
    typeof line['base_price_minor'] === 'number' &&
    Number.isSafeInteger(line['base_price_minor']) &&
    line['base_price_minor'] >= 0 &&
    typeof line['quantity'] === 'number' &&
    Number.isSafeInteger(line['quantity']) &&
    line['quantity'] >= 1 &&
    line['quantity'] <= MAX_LINE_QUANTITY &&
    (line['item_instructions'] === null ||
      typeof line['item_instructions'] === 'string') &&
    Array.isArray(line['options']) &&
    (line['options'] as unknown[]).every(isCartOption)
  );
}

/**
 * Parse a persisted cart. Anything that is not exactly the current
 * schema — wrong version, malformed JSON, structural mismatch — is an
 * empty cart, never an error: a stale cart is dropped, not repaired.
 */
export function parseCart(raw: string | null): Cart {
  if (raw === null) return emptyCart();
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return emptyCart();
  }
  if (typeof parsed !== 'object' || parsed === null) return emptyCart();
  const candidate = parsed as Record<string, unknown>;
  if (candidate['schema_version'] !== CART_SCHEMA_VERSION) return emptyCart();
  if (!Array.isArray(candidate['lines'])) return emptyCart();
  const lines = candidate['lines'] as unknown[];
  if (!lines.every(isCartLine) || lines.length > MAX_CART_LINES) {
    return emptyCart();
  }
  return { schema_version: CART_SCHEMA_VERSION, lines: lines as CartLine[] };
}

export function serializeCart(cart: Cart): string {
  return JSON.stringify(cart);
}
