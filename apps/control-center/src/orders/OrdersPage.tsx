import { useEffect, useMemo, useRef, useState } from 'react';
import type {
  AdminOrderSummary,
  OrderStatus,
} from '@restaurant-engine/api-client';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { Dialog } from '../components/Dialog';
import { CheckboxField, FormField, SelectField } from '../components/FormField';
import { useNotify } from '../components/NotificationProvider';
import { ErrorSummary } from '../components/StatusPanels';
import type { FormFailure } from '../components/formErrors';
import { useHoursSettings } from '../hours/hoursData';
import { formatMinor } from '../menu/money';
import { OrderDrawer } from './OrderDrawer';
import {
  ordersFailure,
  useIncomingOrders,
  useOrderMetrics,
  useOrdersList,
  useSetOrderingPause,
} from './ordersData';
import {
  STATUS_LABELS,
  businessDay,
  formatInstant,
  isOverdue,
  orderAge,
} from './orderFormat';
import { ordersPermissions } from './permissions';
import styles from './orders.module.css';

/** The chime opt-in, per device (ADR-027 ruling D10): off by default. */
export const CHIME_STORAGE_KEY = 'restaurant-engine.order-chime';

// The board's status filters (docs/08: New/Accepted/Preparing/Ready in
// operational language; finished orders behind their own filter). The
// default view is "All active" — the whole service at a glance,
// deliberately undated, because an order placed before midnight that is
// still preparing is still today's work.
const ACTIVE_STATUSES: readonly OrderStatus[] = [
  'submitted',
  'accepted',
  'preparing',
  'ready',
];
const FILTERS = [
  { key: 'active', label: 'All active', statuses: ACTIVE_STATUSES },
  { key: 'new', label: 'New', statuses: ['submitted'] as const },
  { key: 'accepted', label: 'Accepted', statuses: ['accepted'] as const },
  { key: 'preparing', label: 'Preparing', statuses: ['preparing'] as const },
  { key: 'ready', label: 'Ready', statuses: ['ready'] as const },
  {
    key: 'finished',
    label: 'Finished',
    statuses: ['completed', 'rejected', 'cancelled'] as const,
  },
] as const;

type FilterKey = (typeof FILTERS)[number]['key'];

/** Honest per-filter empty copy: what is absent, not a generic shrug. */
const EMPTY_COPY: Record<FilterKey, string> = {
  active: 'No active orders right now.',
  new: 'No new orders right now.',
  accepted: 'No accepted orders waiting to start.',
  preparing: 'Nothing is being prepared right now.',
  ready: 'Nothing is waiting for pickup.',
  finished: 'Nothing finished in this view yet.',
};

function chimeEnabled(): boolean {
  try {
    return window.localStorage.getItem(CHIME_STORAGE_KEY) === 'on';
  } catch {
    return false;
  }
}

/** A short attention beep via the Web Audio API — no asset, no autoplay
 *  (the enabling click was the user gesture, D10). */
function playChime(): void {
  try {
    const Ctor = window.AudioContext;
    if (typeof Ctor !== 'function') {
      return;
    }
    const context = new Ctor();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 880;
    gain.gain.value = 0.06;
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.2);
    oscillator.onended = () => {
      void context.close();
    };
  } catch {
    // A blocked or absent audio stack never breaks the board.
  }
}

const RESUME_CHOICES = [
  { value: '', label: 'No set time' },
  { value: '30', label: 'In 30 minutes' },
  { value: '60', label: 'In 1 hour' },
  { value: '120', label: 'In 2 hours' },
  { value: '240', label: 'In 4 hours' },
] as const;

/**
 * The live order board (M7C, ADR-027): every role operates it (the D2
 * capability), it polls (ruling D9 — the §14.3 doctrine's first
 * consumer), it makes new orders impossible to miss (ruling D10), and
 * nothing here mutates status except the named commands in the drawer.
 */
export function OrdersPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const session = useSession();
  const notify = useNotify();
  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;

  const [filterKey, setFilterKey] = useState<FilterKey>('active');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [day, setDay] = useState('');
  const [openOrderId, setOpenOrderId] = useState<string | null>(null);
  const [newArrivals, setNewArrivals] = useState(0);
  const [chime, setChime] = useState(chimeEnabled);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [pauseNote, setPauseNote] = useState('');
  const [pauseResume, setPauseResume] = useState('');
  const [pauseFailure, setPauseFailure] = useState<FormFailure | null>(null);
  // Seen submitted ids, for the poll-diff new-order alert (D10). Null
  // until the first watch answers, so opening the board never alerts.
  const seenSubmitted = useRef<Set<string> | null>(null);
  // A 30 s tick so order ages stay honest between polls.
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 30_000);
    return () => {
      clearInterval(timer);
    };
  }, []);

  // Debounced search → the D6 `q` filter.
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
    }, 300);
    return () => {
      clearTimeout(timer);
    };
  }, [search]);

  const activeFilter =
    FILTERS.find((entry) => entry.key === filterKey) ?? FILTERS[0];
  const filters = useMemo(
    () => ({ statuses: activeFilter.statuses, q: query, day }),
    [activeFilter, query, day],
  );
  const list = useOrdersList(businessId, filters);
  const incoming = useIncomingOrders(businessId);
  const metrics = useOrderMetrics(businessId);
  const hours = useHoursSettings(businessId);
  const setPause = useSetOrderingPause(businessId);

  // The poll-diff alert (D10) rides the filter-independent watch: an
  // order arriving while someone reads the Ready column still shouts.
  const incomingOrders = incoming.data?.orders;
  useEffect(() => {
    if (incomingOrders === undefined) {
      return;
    }
    const ids = incomingOrders.map((order) => order.id);
    if (seenSubmitted.current === null) {
      seenSubmitted.current = new Set(ids);
      return;
    }
    const seen = seenSubmitted.current;
    const unseen = ids.filter((id) => !seen.has(id));
    for (const id of unseen) {
      seen.add(id);
    }
    if (unseen.length > 0) {
      setNewArrivals((count) => count + unseen.length);
      if (chimeEnabled()) {
        playChime();
      }
    }
  }, [incomingOrders]);

  if (membership === null) {
    return null; // The guard owns this case.
  }
  const permissions = ordersPermissions(membership);
  const fulfillment = hours.data?.fulfillment;
  const paused = fulfillment?.ordering_paused === true;
  // The hours settings document is the timezone authority; the metrics
  // read carries the business currency, so an empty board still prints
  // money in the right unit.
  const timezone = hours.data?.timezone ?? 'UTC';
  const orders: AdminOrderSummary[] =
    list.data?.pages.flatMap((page) => page.orders) ?? [];
  const newCount = incoming.data?.orders.length ?? 0;
  const newCountLabel =
    incoming.data?.next_before_number === null || incoming.data === undefined
      ? String(newCount)
      : `${String(newCount)}+`;

  const submitPause = (body: {
    paused: boolean;
    note?: string;
    resume_at?: string;
  }): void => {
    setPauseFailure(null);
    setPause.mutate(body, {
      onSuccess: () => {
        setPauseDialogOpen(false);
        setPauseNote('');
        setPauseResume('');
        notify({
          message: body.paused ? 'Ordering paused.' : 'Ordering resumed.',
        });
      },
      onError: (error: unknown) => {
        setPauseFailure(
          ordersFailure(error, 'The pause could not be updated.'),
        );
      },
    });
  };

  return (
    <section aria-labelledby="orders-title" className={styles.page}>
      <h2 id="orders-title">Orders</h2>

      {metrics.data === undefined ? null : (
        <div className={styles.metricsPanel}>
          <h3 className={styles.metricsHeading}>Today</h3>
          <dl className={styles.metricsStrip}>
            <div className={styles.metric}>
              <dt>Orders</dt>
              <dd>{metrics.data.order_count}</dd>
            </div>
            <div className={styles.metric}>
              <dt>Sales</dt>
              <dd>
                {formatMinor(metrics.data.sales_minor, metrics.data.currency)}
              </dd>
            </div>
            <div className={styles.metric}>
              <dt>Average order</dt>
              <dd>
                {metrics.data.average_order_value_minor === null
                  ? '—'
                  : formatMinor(
                      metrics.data.average_order_value_minor,
                      metrics.data.currency,
                    )}
              </dd>
            </div>
            <div className={styles.metric}>
              <dt>Declined or cancelled</dt>
              <dd>
                {metrics.data.rejected_count + metrics.data.cancelled_count}
              </dd>
            </div>
            <div className={styles.metric}>
              <dt>Average prep</dt>
              <dd>
                {metrics.data.average_prep_seconds === null
                  ? '—'
                  : `${String(Math.round(metrics.data.average_prep_seconds / 60))}m`}
              </dd>
            </div>
            {metrics.data.popular_items[0] === undefined ? null : (
              <div className={styles.metric}>
                <dt>Most ordered</dt>
                <dd>{metrics.data.popular_items[0].display_name}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {paused && fulfillment !== undefined ? (
        <div className={styles.pauseBanner}>
          <p className={styles.pauseText}>
            <strong>Ordering is paused.</strong>{' '}
            {fulfillment.pause_note === null
              ? 'Customers see that you are not taking orders right now.'
              : `Customers see: “${fulfillment.pause_note}”`}
            {fulfillment.pause_resume_at === null
              ? ''
              : ` Back around ${formatInstant(fulfillment.pause_resume_at, timezone)}.`}
          </p>
          {permissions.canPause ? (
            <button
              type="button"
              className={styles.secondary}
              disabled={setPause.isPending}
              onClick={() => {
                submitPause({ paused: false });
              }}
            >
              Resume ordering
            </button>
          ) : null}
        </div>
      ) : null}
      {pauseFailure !== null && !pauseDialogOpen ? (
        <ErrorSummary failure={pauseFailure} />
      ) : null}

      <div className={styles.controlsRow}>
        <div
          className={styles.filters}
          role="group"
          aria-label="Filter orders by status"
        >
          {FILTERS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              aria-pressed={filterKey === entry.key}
              className={`${styles.filterChip} ${
                filterKey === entry.key ? styles.filterChipOn : ''
              }`}
              onClick={() => {
                setFilterKey(entry.key);
              }}
            >
              {entry.label}
              {entry.key === 'new' && newCount > 0 ? (
                <span className={styles.newBadge}>{newCountLabel}</span>
              ) : null}
            </button>
          ))}
        </div>
        <div className={styles.searchField}>
          <FormField
            id="orders-search"
            label="Search"
            type="search"
            placeholder="Order # or customer"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
        </div>
        <div className={styles.dayField}>
          <FormField
            id="orders-day"
            label="Day"
            type="date"
            value={day}
            max={businessDay(now, timezone)}
            onChange={(event) => {
              setDay(event.target.value);
            }}
          />
        </div>
        {day === '' ? null : (
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              setDay('');
            }}
          >
            Back to live
          </button>
        )}
        <div className={styles.chimeField}>
          <CheckboxField
            id="orders-chime"
            label="New-order sound"
            checked={chime}
            onChange={(event) => {
              const on = event.target.checked;
              setChime(on);
              try {
                if (on) {
                  window.localStorage.setItem(CHIME_STORAGE_KEY, 'on');
                } else {
                  window.localStorage.removeItem(CHIME_STORAGE_KEY);
                }
              } catch {
                // Persistence is best-effort; the toggle still works.
              }
            }}
          />
        </div>
        {permissions.canPause && !paused ? (
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              setPauseFailure(null);
              setPauseDialogOpen(true);
            }}
          >
            Pause ordering…
          </button>
        ) : null}
      </div>

      {query === '' ? null : (
        <p className={styles.viewNote}>
          Showing every status matching “{query}”.
        </p>
      )}
      {day === '' || query !== '' ? null : (
        <p className={styles.viewNote}>
          Showing one past day. Live updates resume when you go back to live.
        </p>
      )}

      {/* The live region is always mounted, so an arrival is an update to
          announce rather than a region appearing (ruling D10). */}
      <div role="status" className={styles.alertRegion}>
        {newArrivals > 0 ? (
          <span className={styles.newOrderAlert}>
            <strong>
              {newArrivals === 1
                ? '1 new order'
                : `${String(newArrivals)} new orders`}
            </strong>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => {
                setNewArrivals(0);
                setFilterKey('new');
                setDay('');
              }}
            >
              Show new orders
            </button>
          </span>
        ) : null}
      </div>

      {list.isPending ? (
        <p role="status" className={styles.loading}>
          Loading orders…
        </p>
      ) : list.isError ? (
        <div role="alert" className={styles.errorPanel}>
          <p>The orders could not be loaded.</p>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void list.refetch();
            }}
          >
            Try again
          </button>
        </div>
      ) : orders.length === 0 ? (
        <p className={styles.empty}>
          {query !== ''
            ? 'No orders match that search.'
            : day !== ''
              ? 'No orders on that day.'
              : EMPTY_COPY[filterKey]}
        </p>
      ) : (
        <>
          <ul className={styles.tickets}>
            {orders.map((order) => (
              <li key={order.id}>
                <button
                  type="button"
                  className={styles.ticket}
                  onClick={() => {
                    setOpenOrderId(order.id);
                  }}
                >
                  <span className={styles.ticketHeader}>
                    <span className={styles.ticketNumber}>
                      #{order.order_number}
                    </span>
                    <span
                      className={`${styles.statusBadge} ${
                        order.status === 'submitted' ? styles.statusNew : ''
                      }`}
                    >
                      {STATUS_LABELS[order.status]}
                    </span>
                  </span>
                  <span className={styles.ticketMeta}>
                    <span>{order.customer_name}</span>
                    <span>{orderAge(order.placed_at, now)}</span>
                    {/* The kitchen's own estimate outranks the promise
                        once it exists, and says which one it is. */}
                    <span>
                      {order.estimated_ready_at === null
                        ? `Pickup ${formatInstant(order.promised_pickup_at, timezone)}`
                        : `Ready ${formatInstant(order.estimated_ready_at, timezone)}`}
                    </span>
                    {isOverdue(order, now) ? (
                      <span className={styles.overdue}>Overdue</span>
                    ) : null}
                    <span>
                      {formatMinor(order.total_minor, order.currency)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {list.hasNextPage ? (
            <button
              type="button"
              className={styles.secondary}
              disabled={list.isFetchingNextPage}
              onClick={() => {
                void list.fetchNextPage();
              }}
            >
              {list.isFetchingNextPage ? 'Loading…' : 'Load older orders'}
            </button>
          ) : null}
        </>
      )}

      {openOrderId === null ? null : (
        <OrderDrawer
          businessId={businessId}
          orderId={openOrderId}
          orderNumber={
            orders.find((order) => order.id === openOrderId)?.order_number ??
            null
          }
          timezone={timezone}
          onClose={() => {
            setOpenOrderId(null);
          }}
        />
      )}

      {pauseDialogOpen ? (
        <Dialog
          title="Pause ordering"
          pending={setPause.isPending}
          onCancel={() => {
            setPauseDialogOpen(false);
          }}
        >
          {pauseFailure !== null ? (
            <ErrorSummary failure={pauseFailure} />
          ) : null}
          <p className={styles.mutedText}>
            Customers see the pause and your note on the ordering page; carts
            they have already started are kept.
          </p>
          <FormField
            id="pause-note"
            label="Customer-visible note (optional)"
            type="text"
            maxLength={300}
            value={pauseNote}
            onChange={(event) => {
              setPauseNote(event.target.value);
            }}
          />
          {/* Durations, never a wall-clock picker: the device's timezone
              is not necessarily the restaurant's, and "in an hour" is
              what a paused kitchen actually means. */}
          <SelectField
            id="pause-resume"
            label="Resume"
            hint="Ordering reopens by itself at this point; you can resume sooner."
            value={pauseResume}
            onChange={(event) => {
              setPauseResume(event.target.value);
            }}
          >
            {RESUME_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </SelectField>
          <div className={styles.actionsRow}>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => {
                setPauseDialogOpen(false);
              }}
            >
              Keep ordering on
            </button>
            <button
              type="button"
              className={styles.primary}
              disabled={setPause.isPending}
              onClick={() => {
                const trimmed = pauseNote.trim();
                const minutes = Number(pauseResume);
                submitPause({
                  paused: true,
                  ...(trimmed === '' ? {} : { note: trimmed }),
                  ...(pauseResume === ''
                    ? {}
                    : {
                        resume_at: new Date(
                          Date.now() + minutes * 60_000,
                        ).toISOString(),
                      }),
                });
              }}
            >
              Pause ordering
            </button>
          </div>
        </Dialog>
      ) : null}
    </section>
  );
}
