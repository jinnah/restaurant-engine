import { useEffect, useRef, useState } from 'react';
import type {
  AdminOrderDetail,
  OrderStatus,
} from '@restaurant-engine/api-client';
import { Dialog } from '../components/Dialog';
import { useNotify } from '../components/NotificationProvider';
import { formatMinor } from '../menu/money';
import {
  isInvalidState,
  useOrderCommand,
  useOrderDetail,
  useSetEstimate,
  type OrderCommand,
} from './ordersData';
import { STATUS_LABELS, formatClock, formatInstant } from './orderFormat';
import styles from './orders.module.css';

interface CommandAction {
  command: OrderCommand;
  label: string;
  /** Present when the action deserves a deliberate second step. */
  confirm?: string;
}

/** The legal next commands per status (the §7.7 machine, D1/D4): the
 *  drawer offers exactly these and nothing else — a raced refusal is
 *  the server's to make and the board's to refetch. */
const LEGAL_COMMANDS: Partial<Record<OrderStatus, CommandAction[]>> = {
  submitted: [
    { command: 'accept', label: 'Accept' },
    {
      command: 'reject',
      label: 'Decline',
      confirm: 'Decline this order? The customer sees it immediately.',
    },
    {
      command: 'cancel',
      label: 'Cancel',
      confirm:
        'Cancel this order for the customer? Use this when they asked you to.',
    },
  ],
  accepted: [{ command: 'startPreparing', label: 'Start preparing' }],
  preparing: [{ command: 'markReady', label: 'Mark ready' }],
  ready: [{ command: 'complete', label: 'Complete' }],
};

const ESTIMATE_LEGAL: readonly OrderStatus[] = ['accepted', 'preparing'];

/** Minutes from now — a kitchen thinks in "twenty more minutes", and a
 *  duration cannot be misread by a device sitting in another timezone. */
const ESTIMATE_CHOICES = [10, 15, 20, 30, 45] as const;

const SUCCESS_MESSAGES: Record<OrderCommand, string> = {
  accept: 'Order accepted.',
  reject: 'Order declined.',
  startPreparing: 'Order is now preparing.',
  markReady: 'Order marked ready.',
  complete: 'Order completed.',
  cancel: 'Order cancelled.',
};

const CONFIRM_TEXT_ID = 'order-confirm-text';

/** The instant a duration means, read at the moment the kitchen says it. */
function minutesFromNowIso(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toISOString();
}

/**
 * The order detail drawer (M7C, ADR-027 D6): the full counter
 * projection — PII on purpose, under the named capability — the
 * append-only timeline, the guarded commands, the D7 estimate control,
 * and the D12 print ticket.
 *
 * A consequential command confirms *inside* this dialog rather than
 * opening a second one: the control center keeps exactly one dialog
 * open at a time, and a nested dialog would put two focus traps and two
 * elements carrying the same title id on the page at once.
 */
export function OrderDrawer({
  businessId,
  orderId,
  orderNumber,
  timezone,
  onClose,
}: {
  businessId: string;
  orderId: string;
  /** Known from the ticket that opened this, so the title is right at once. */
  orderNumber: number | null;
  timezone: string;
  onClose: () => void;
}) {
  const notify = useNotify();
  const detail = useOrderDetail(businessId, orderId);
  const accept = useOrderCommand(businessId, 'accept');
  const reject = useOrderCommand(businessId, 'reject');
  const startPreparing = useOrderCommand(businessId, 'startPreparing');
  const markReady = useOrderCommand(businessId, 'markReady');
  const complete = useOrderCommand(businessId, 'complete');
  const cancel = useOrderCommand(businessId, 'cancel');
  const setEstimate = useSetEstimate(businessId);
  const [confirming, setConfirming] = useState<CommandAction | null>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirming !== null) {
      confirmRef.current?.focus();
    }
  }, [confirming]);

  const mutations: Record<OrderCommand, ReturnType<typeof useOrderCommand>> = {
    accept,
    reject,
    startPreparing,
    markReady,
    complete,
    cancel,
  };
  const anyPending =
    Object.values(mutations).some((mutation) => mutation.isPending) ||
    setEstimate.isPending;

  const run = (command: OrderCommand): void => {
    mutations[command].mutate(orderId, {
      onSuccess: () => {
        notify({ message: SUCCESS_MESSAGES[command] });
      },
      onError: (error: unknown) => {
        notify({
          message: isInvalidState(error)
            ? 'This order changed on another device — showing the latest.'
            : 'That could not be done — try again.',
        });
      },
    });
  };

  const sendEstimate = (minutes: number | null): void => {
    setEstimate.mutate(
      {
        orderId,
        body: {
          estimated_ready_at:
            minutes === null ? null : minutesFromNowIso(minutes),
        },
      },
      {
        onSuccess: () => {
          notify({
            message: minutes === null ? 'Estimate cleared.' : 'Estimate set.',
          });
        },
        onError: () => {
          notify({
            message: 'The estimate could not be saved — showing the latest.',
          });
        },
      },
    );
  };

  const order: AdminOrderDetail | undefined = detail.data;

  return (
    <Dialog
      title={orderNumber === null ? 'Order' : `Order #${String(orderNumber)}`}
      className={styles.drawer}
      pending={anyPending}
      onCancel={onClose}
    >
      {detail.isPending ? (
        <p role="status" className={styles.loading}>
          Loading order…
        </p>
      ) : detail.isError || order === undefined ? (
        <div role="alert" className={styles.errorPanel}>
          <p>The order could not be loaded.</p>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void detail.refetch();
            }}
          >
            Try again
          </button>
        </div>
      ) : (
        <>
          <div className={styles.drawerSection}>
            <p className={styles.drawerStatus}>
              <span className={styles.statusBadge}>
                {STATUS_LABELS[order.status]}
              </span>
            </p>
            <dl className={styles.detailList}>
              <dt>Customer</dt>
              <dd>{order.customer_name}</dd>
              <dt>Phone</dt>
              <dd>{order.customer_phone}</dd>
              {order.customer_email === null ? null : (
                <>
                  <dt>Email</dt>
                  <dd>{order.customer_email}</dd>
                </>
              )}
              <dt>Placed</dt>
              <dd>{formatInstant(order.placed_at, timezone)}</dd>
              <dt>Pickup</dt>
              <dd>
                {formatInstant(order.promised_pickup_at, timezone)}
                {order.pickup_kind === 'asap' ? ' (ASAP)' : ''}
              </dd>
              {order.estimated_ready_at === null ? null : (
                <>
                  <dt>Estimated ready</dt>
                  <dd>{formatInstant(order.estimated_ready_at, timezone)}</dd>
                </>
              )}
              <dt>Payment</dt>
              <dd>Pay at pickup</dd>
              <dt>Source</dt>
              <dd>Online</dd>
              <dt>Order updates OK</dt>
              <dd>{order.consent_updates ? 'Yes' : 'No'}</dd>
              <dt>Marketing OK</dt>
              <dd>{order.consent_marketing ? 'Yes' : 'No'}</dd>
            </dl>
            {order.order_instructions === null ? null : (
              <p className={styles.instructions}>
                “{order.order_instructions}”
              </p>
            )}
          </div>

          <div className={styles.drawerSection}>
            <ul className={styles.lines}>
              {order.lines.map((line, index) => (
                <li key={index} className={styles.line}>
                  <p className={styles.lineHeader}>
                    <span>
                      {line.quantity} × {line.display_name}
                    </span>
                    <span>
                      {formatMinor(line.line_total_minor, order.currency)}
                    </span>
                  </p>
                  {line.options.length === 0 ? null : (
                    <p className={styles.lineMeta}>
                      {line.options
                        .map((option) => option.option_name)
                        .join(', ')}
                    </p>
                  )}
                  {line.item_instructions === null ? null : (
                    <p className={styles.lineMeta}>
                      “{line.item_instructions}”
                    </p>
                  )}
                </li>
              ))}
            </ul>
            <p className={styles.totalRow}>
              <span>Total</span>
              <span>{formatMinor(order.total_minor, order.currency)}</span>
            </p>
          </div>

          <div className={styles.drawerSection}>
            <h3 className={styles.drawerHeading}>History</h3>
            <ol className={styles.timeline}>
              {order.timeline.map((event, index) => (
                <li key={index}>
                  {STATUS_LABELS[event.to_status]} —{' '}
                  {formatInstant(event.occurred_at, timezone)}
                  {event.actor_kind === 'member' ? ' (staff)' : ''}
                </li>
              ))}
            </ol>
          </div>

          {ESTIMATE_LEGAL.includes(order.status) ? (
            <div className={styles.drawerSection}>
              <div role="group" aria-label="Set an estimated ready time">
                <p className={styles.drawerHeading}>
                  Ready in
                  {order.estimated_ready_at === null
                    ? ''
                    : ` — now ${formatClock(order.estimated_ready_at, timezone)}`}
                </p>
                <div className={styles.actionsRow}>
                  {ESTIMATE_CHOICES.map((minutes) => (
                    <button
                      key={minutes}
                      type="button"
                      className={styles.quiet}
                      disabled={anyPending}
                      onClick={() => {
                        sendEstimate(minutes);
                      }}
                    >
                      {minutes} min
                    </button>
                  ))}
                  {order.estimated_ready_at === null ? null : (
                    <button
                      type="button"
                      className={styles.secondary}
                      disabled={anyPending}
                      onClick={() => {
                        sendEstimate(null);
                      }}
                    >
                      Clear estimate
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : null}

          {confirming === null ? (
            <div className={styles.actionsRow}>
              {(LEGAL_COMMANDS[order.status] ?? []).map((action) => (
                <button
                  key={action.command}
                  type="button"
                  className={
                    action.confirm === undefined
                      ? styles.primary
                      : styles.secondary
                  }
                  disabled={anyPending}
                  onClick={() => {
                    if (action.confirm === undefined) {
                      run(action.command);
                    } else {
                      setConfirming(action);
                    }
                  }}
                >
                  {action.label}
                </button>
              ))}
              <button
                type="button"
                className={styles.secondary}
                onClick={() => {
                  if (typeof window.print === 'function') {
                    window.print();
                  }
                }}
              >
                Print ticket
              </button>
            </div>
          ) : (
            <div className={styles.confirmPanel}>
              <p id={CONFIRM_TEXT_ID}>{confirming.confirm}</p>
              <div className={styles.actionsRow}>
                <button
                  ref={confirmRef}
                  type="button"
                  className={styles.danger}
                  aria-describedby={CONFIRM_TEXT_ID}
                  disabled={anyPending}
                  onClick={() => {
                    run(confirming.command);
                    setConfirming(null);
                  }}
                >
                  {confirming.label} order #{order.order_number}
                </button>
                <button
                  type="button"
                  className={styles.secondary}
                  disabled={anyPending}
                  onClick={() => {
                    setConfirming(null);
                  }}
                >
                  Keep it
                </button>
              </div>
            </div>
          )}

          {/* The D12 ticket: print CSS, not a document pipeline. Hidden
              on screen by `display: none`, so it is out of the
              accessibility tree without an aria-hidden that would lie
              about it while it is printing. */}
          <section aria-label="Print ticket" className={styles.printTicket}>
            <h2>#{order.order_number}</h2>
            <p>
              {order.customer_name} · {order.customer_phone}
            </p>
            <p>
              Pickup {formatInstant(order.promised_pickup_at, timezone)}
              {order.pickup_kind === 'asap' ? ' (ASAP)' : ''}
            </p>
            <ul>
              {order.lines.map((line, index) => (
                <li key={index}>
                  {line.quantity} × {line.display_name}
                  {line.options.length === 0
                    ? ''
                    : ` — ${line.options.map((option) => option.option_name).join(', ')}`}
                  {line.item_instructions === null
                    ? ''
                    : ` — “${line.item_instructions}”`}
                </li>
              ))}
            </ul>
            {order.order_instructions === null ? null : (
              <p>“{order.order_instructions}”</p>
            )}
          </section>
        </>
      )}
    </Dialog>
  );
}
