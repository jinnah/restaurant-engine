'use client';

// The order tracker (M6C, ADR-026): polls the public tracking GET at a
// modest interval (the blueprint's polling doctrine — M7's board uses
// the same) and offers customer cancellation while the order is still
// `submitted` (D11), behind an explicit two-step confirmation. Polling
// stops once the status is terminal. A 404 is the honest "not found"
// state: the token is wrong, the host is wrong, or the business is no
// longer publicly visible — indistinguishable by design.

import { useCallback, useEffect, useRef, useState } from 'react';

import type { PublicOrderView } from '@restaurant-engine/api-client';
import { formatMinorUnits } from '@restaurant-engine/storefront-renderer/money';

import { formatInstant } from '../../lib/ordering/format';
import { cancelOrder, getOrder } from '../../lib/ordering/public-api';
import styles from './ordering.module.css';

export const POLL_INTERVAL_MS = 15_000;

const TERMINAL_STATUSES = new Set(['cancelled', 'completed', 'rejected']);

const STATUS_TEXT: Record<string, string> = {
  submitted: 'Order received',
  accepted: 'Accepted by the restaurant',
  preparing: 'Being prepared',
  ready: 'Ready for pickup',
  completed: 'Picked up',
  rejected: 'Declined by the restaurant',
  cancelled: 'Cancelled',
};

type TrackerState =
  | { kind: 'loading' }
  | { kind: 'not-found' }
  | { kind: 'unavailable' }
  | { kind: 'order'; order: PublicOrderView };

export function OrderTracker({ token }: { token: string }) {
  const [state, setState] = useState<TrackerState>({ kind: 'loading' });
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [cancelRefused, setCancelRefused] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const refresh = useCallback(async (): Promise<void> => {
    const result = await getOrder(token);
    if (result.ok) {
      setState({ kind: 'order', order: result.data });
      if (TERMINAL_STATUSES.has(result.data.status)) {
        stopPolling();
      }
      return;
    }
    if (result.status === 404) {
      setState({ kind: 'not-found' });
      stopPolling();
      return;
    }
    // Transient failure: keep the last known order on screen if there
    // is one; otherwise say so honestly. Polling continues.
    setState((current) =>
      current.kind === 'order' ? current : { kind: 'unavailable' },
    );
  }, [token, stopPolling]);

  useEffect(() => {
    const tick = (): void => {
      void refresh();
    };
    // The first read is deferred a tick; every later one rides the
    // polling interval.
    queueMicrotask(tick);
    timer.current = setInterval(tick, POLL_INTERVAL_MS);
    return stopPolling;
  }, [refresh, stopPolling]);

  const handleCancel = async (): Promise<void> => {
    setConfirmingCancel(false);
    const result = await cancelOrder(token);
    if (result.ok) {
      setState({ kind: 'order', order: result.data });
      stopPolling();
      return;
    }
    if (result.status === 409) {
      // The order moved past `submitted` while the page was open; the
      // next read shows where it actually is.
      setCancelRefused(true);
      await refresh();
      return;
    }
    if (result.status === 404) {
      setState({ kind: 'not-found' });
      stopPolling();
    }
  };

  if (state.kind === 'loading') {
    return (
      <div className={styles.surface}>
        <h2 className={styles.surfaceHeading}>Order status</h2>
        <p className={styles.emptyState}>Looking up your order…</p>
      </div>
    );
  }
  if (state.kind === 'not-found') {
    return (
      <div className={styles.surface}>
        <h2 className={styles.surfaceHeading}>Order status</h2>
        <p className={styles.emptyState}>
          No order was found for this link. Check that the address matches the
          one on your confirmation.
        </p>
      </div>
    );
  }
  if (state.kind === 'unavailable') {
    return (
      <div className={styles.surface}>
        <h2 className={styles.surfaceHeading}>Order status</h2>
        <p className={styles.emptyState}>
          Your order could not be loaded right now — this page keeps retrying
          automatically.
        </p>
      </div>
    );
  }

  const { order } = state;
  return (
    <div className={styles.surface}>
      <h2 className={styles.surfaceHeading}>
        Order #{String(order.order_number)}
      </h2>
      <p className={styles.trackerSection}>
        <span role="status" className={styles.statusBadge}>
          {STATUS_TEXT[order.status] ?? order.status}
        </span>
      </p>
      <p className={styles.trackerSection}>
        Pickup:{' '}
        {formatInstant(order.promised_pickup_at, order.business_timezone)}
        {order.pickup_kind === 'asap' ? ' (as soon as possible)' : ''}
      </p>
      <ul className={styles.cartLines}>
        {order.lines.map((line, index) => (
          <li
            key={`${line.display_name}-${String(index)}`}
            className={styles.cartLine}
          >
            <p className={styles.cartLineHeader}>
              <span className={styles.cartLineName}>
                {String(line.quantity)} × {line.display_name}
              </span>
              <span>
                {formatMinorUnits(line.line_total_minor, order.currency)}
              </span>
            </p>
            {line.options.length === 0 ? null : (
              <p className={styles.cartLineMeta}>
                {line.options.map((option) => option.option_name).join(', ')}
              </p>
            )}
          </li>
        ))}
      </ul>
      <p className={styles.totalRow}>
        <span>Total</span>
        <span>{formatMinorUnits(order.total_minor, order.currency)}</span>
      </p>
      {cancelRefused ? (
        <p className={styles.problem}>
          This order can no longer be cancelled online — the restaurant has
          already started on it.
        </p>
      ) : null}
      {order.status === 'submitted' ? (
        confirmingCancel ? (
          <div className={styles.dialogActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => {
                setConfirmingCancel(false);
              }}
            >
              Keep my order
            </button>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={() => {
                void handleCancel();
              }}
            >
              Yes, cancel it
            </button>
          </div>
        ) : (
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => {
              setConfirmingCancel(true);
            }}
          >
            Cancel this order
          </button>
        )
      ) : null}
    </div>
  );
}
