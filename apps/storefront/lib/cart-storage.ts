// Cart persistence (M6C, ADR-026 D13): localStorage under the tenant
// origin. Isolation is structural — the browser scopes localStorage to
// the origin, and every tenant is its own origin — so no tenant key,
// slug, or host ever appears in the storage key. Storage failures
// (privacy modes, quota) degrade to an in-memory-only cart: ordering
// still works within the page; persistence is best-effort.
//
// Islands are separate client roots with no shared React tree, so cart
// changes are announced with a window event; anything presenting cart
// state (the menu page's cart link) re-reads on that signal.

import { emptyCart, parseCart, serializeCart, type Cart } from './cart';

export const CART_STORAGE_KEY = 'restaurant-engine.cart';
export const CART_CHANGED_EVENT = 'restaurant-engine:cart-changed';

export function loadCart(): Cart {
  try {
    return parseCart(window.localStorage.getItem(CART_STORAGE_KEY));
  } catch {
    return emptyCart();
  }
}

export function saveCart(cart: Cart): void {
  try {
    window.localStorage.setItem(CART_STORAGE_KEY, serializeCart(cart));
  } catch {
    // Best-effort persistence; the announcement still fires so the
    // page's presentation stays coherent with what the user did.
  }
  window.dispatchEvent(new Event(CART_CHANGED_EVENT));
}

export function clearStoredCart(): void {
  try {
    window.localStorage.removeItem(CART_STORAGE_KEY);
  } catch {
    // Nothing to recover; the event still announces the change.
  }
  window.dispatchEvent(new Event(CART_CHANGED_EVENT));
}
