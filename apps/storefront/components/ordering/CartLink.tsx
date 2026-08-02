'use client';

// The menu page's route to checkout (M6C): a fixed "View order" link
// that appears once the cart holds anything. Islands are separate
// client roots, so the count listens for the storage layer's change
// event rather than sharing React state.

import { useEffect, useState } from 'react';

import { cartItemCount } from '../../lib/cart';
import { CART_CHANGED_EVENT, loadCart } from '../../lib/cart-storage';
import styles from './ordering.module.css';

export function CartLink() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const refresh = (): void => {
      setCount(cartItemCount(loadCart()));
    };
    refresh();
    window.addEventListener(CART_CHANGED_EVENT, refresh);
    return () => {
      window.removeEventListener(CART_CHANGED_EVENT, refresh);
    };
  }, []);

  if (count === 0) {
    return null;
  }
  return (
    <a href="/order" className={styles.cartLink}>
      View order ({String(count)})
    </a>
  );
}
