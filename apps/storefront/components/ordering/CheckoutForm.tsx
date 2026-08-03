'use client';

// Checkout (M6C, ADR-026): cart review, contact, pickup promise, the
// two independent consents (D7 — never pre-checked, never blended), and
// honest failure states for every typed 409 the placement command can
// answer. The displayed total is submitted as `expected_total_minor`
// (D8) — compared by the server, never believed.
//
// Idempotency (D2): one key per submission *content*. The key is minted
// at submit when none is held, kept across pure retries of the same
// payload (a retry returns the same order), and dropped the moment any
// payload-relevant state changes — the same key with a different cart
// is the server's `idempotency_key_reused` refusal, not an honest retry.

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Route } from 'next';
import { useRouter } from 'next/navigation';

import type { OrderPlace } from '@restaurant-engine/api-client';
import { formatMinorUnits } from '@restaurant-engine/storefront-renderer/money';

import {
  cartTotalMinor,
  lineTotalMinor,
  removeLine,
  setLineQuantity,
  toPlacementLines,
  MAX_LINE_QUANTITY,
  type Cart,
} from '../../lib/cart';
import { clearStoredCart, loadCart, saveCart } from '../../lib/cart-storage';
import { formatInstant } from '../../lib/ordering/format';
import { getPickupSlots, placeOrder } from '../../lib/ordering/public-api';
import styles from './ordering.module.css';

const MAX_NAME = 120;
const MAX_PHONE = 40;
const MAX_EMAIL = 254;
const MAX_ORDER_INSTRUCTIONS = 500;

// The M6A staleness vocabulary, presented honestly per line.
const PROBLEM_TEXT: Record<string, string> = {
  item_unknown: 'This item is no longer on the menu.',
  item_unavailable: 'This item is sold out right now.',
  item_not_orderable: 'This item cannot be ordered right now.',
  option_unknown: 'A chosen option is no longer offered.',
  option_unavailable: 'A chosen option is unavailable right now.',
  option_duplicate: 'An option was selected twice.',
  selection_rule: 'The chosen options no longer satisfy this item’s rules.',
  total_bounds: 'This order is too large to place online.',
};

interface LineProblem {
  reason: string;
  line_index: number | null;
}

type SubmitState =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'stale'; problems: LineProblem[] }
  | { kind: 'price-changed'; totalMinor: number; expectedMinor: number }
  | { kind: 'slot-unavailable' }
  | { kind: 'key-reused' }
  | { kind: 'paused'; note: string | null; resumeAt: string | null }
  | { kind: 'gone' }
  | { kind: 'failed' };

function parseProblems(details: Record<string, unknown> | null): LineProblem[] {
  const raw = details?.['problems'];
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    if (typeof entry !== 'object' || entry === null) return [];
    const problem = entry as Record<string, unknown>;
    const reason = problem['reason'];
    if (typeof reason !== 'string') return [];
    const index = problem['line_index'];
    return [
      {
        reason,
        line_index: typeof index === 'number' ? index : null,
      },
    ];
  });
}

export function CheckoutForm({
  currency,
  timezone,
  asapEnabled,
}: {
  currency: string;
  timezone: string;
  asapEnabled: boolean;
}) {
  const router = useRouter();
  const [cart, setCart] = useState<Cart | null>(null);
  const [slots, setSlots] = useState<string[] | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [instructions, setInstructions] = useState('');
  const [pickupKind, setPickupKind] = useState<'asap' | 'scheduled'>(
    asapEnabled ? 'asap' : 'scheduled',
  );
  const [slot, setSlot] = useState('');
  const [consentUpdates, setConsentUpdates] = useState(false);
  const [consentMarketing, setConsentMarketing] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submit, setSubmit] = useState<SubmitState>({ kind: 'idle' });
  // The held idempotency key; null means "mint a fresh one at submit".
  const idempotencyKey = useRef<string | null>(null);

  useEffect(() => {
    // Deferred a tick: the stored cart exists only client-side, so the
    // first paint is the hydration-safe loading state either way.
    queueMicrotask(() => {
      setCart(loadCart());
    });
    void getPickupSlots().then((result) => {
      setSlots(result.ok ? result.data.slots : []);
    });
  }, []);

  // Any payload-relevant change invalidates the held key and clears a
  // stale refusal — the next submit is a new command, honestly.
  const invalidateKey = useCallback(() => {
    idempotencyKey.current = null;
  }, []);

  const updateCart = (next: Cart): void => {
    saveCart(next);
    setCart(next);
    invalidateKey();
    setSubmit((current) =>
      current.kind === 'submitting' ? current : { kind: 'idle' },
    );
  };

  if (cart === null) {
    return (
      <div className={styles.surface}>
        <h2 className={styles.surfaceHeading}>Your order</h2>
        <p className={styles.emptyState}>Loading your order…</p>
      </div>
    );
  }

  if (cart.lines.length === 0 && submit.kind !== 'submitting') {
    return (
      <div className={styles.surface}>
        <h2 className={styles.surfaceHeading}>Your order</h2>
        <p className={styles.emptyState}>
          Your order is empty.{' '}
          <a href="/menu" className={styles.inlineLink}>
            Browse the menu
          </a>{' '}
          to add something.
        </p>
      </div>
    );
  }

  const totalMinor = cartTotalMinor(cart);
  // After a `price_changed` refusal the authoritative total is what the
  // surface displays and what the deliberate retry submits (D8: the
  // expected total is always the total the visitor was shown). Any cart
  // edit returns to the locally computed display total.
  const displayTotalMinor =
    submit.kind === 'price-changed' ? submit.totalMinor : totalMinor;
  const staleProblems = submit.kind === 'stale' ? submit.problems : [];
  const lineProblems = (index: number): LineProblem[] =>
    staleProblems.filter((problem) => problem.line_index === index);
  const cartProblems = staleProblems.filter(
    (problem) => problem.line_index === null,
  );

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (name.trim() === '') errors['name'] = 'Enter a name for the order.';
    if (phone.trim() === '') {
      errors['phone'] = 'Enter a phone number so the restaurant can reach you.';
    }
    if (pickupKind === 'scheduled' && slot === '') {
      errors['slot'] = 'Choose a pickup time.';
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (): Promise<void> => {
    if (!validate()) return;
    idempotencyKey.current ??= crypto.randomUUID();
    const trimmedEmail = email.trim();
    const trimmedInstructions = instructions.trim();
    const payload: OrderPlace = {
      idempotency_key: idempotencyKey.current,
      lines: toPlacementLines(cart),
      customer_name: name.trim(),
      customer_phone: phone.trim(),
      customer_email: trimmedEmail === '' ? null : trimmedEmail,
      order_instructions:
        trimmedInstructions === '' ? null : trimmedInstructions,
      consent_updates: consentUpdates,
      consent_marketing: consentMarketing,
      pickup_kind: pickupKind,
      requested_pickup_at: pickupKind === 'scheduled' ? slot : null,
      expected_total_minor: displayTotalMinor,
    };
    setSubmit({ kind: 'submitting' });
    const result = await placeOrder(payload);
    if (result.ok) {
      clearStoredCart();
      // The dynamic segment defeats the typed-routes literal check; the
      // route exists (app/order/track/[token]) and the token is opaque.
      router.push(
        `/order/track/${encodeURIComponent(result.data.tracking_token)}` as Route,
      );
      return;
    }
    if (result.status === 409 && result.code === 'cart_stale') {
      invalidateKey();
      setSubmit({ kind: 'stale', problems: parseProblems(result.details) });
      return;
    }
    if (result.status === 409 && result.code === 'price_changed') {
      invalidateKey();
      const authoritative = result.details?.['total_minor'];
      setSubmit({
        kind: 'price-changed',
        totalMinor: typeof authoritative === 'number' ? authoritative : 0,
        expectedMinor: displayTotalMinor,
      });
      return;
    }
    if (result.status === 409 && result.code === 'slot_unavailable') {
      invalidateKey();
      setSlot('');
      const refreshed = await getPickupSlots();
      setSlots(refreshed.ok ? refreshed.data.slots : []);
      setSubmit({ kind: 'slot-unavailable' });
      return;
    }
    if (result.status === 409 && result.code === 'ordering_paused') {
      // M7B (ADR-027 D8): a pause can begin mid-checkout. The held key
      // is deliberately KEPT — retrying the same command after the
      // resume is an honest replay, never a duplicate.
      const note = result.details?.['note'];
      const resume = result.details?.['resume_at'];
      setSubmit({
        kind: 'paused',
        note: typeof note === 'string' ? note : null,
        resumeAt: typeof resume === 'string' ? resume : null,
      });
      return;
    }
    if (result.status === 409 && result.code === 'idempotency_key_reused') {
      // The held key pinned an earlier payload; mint fresh and let the
      // visitor place again deliberately.
      invalidateKey();
      setSubmit({ kind: 'key-reused' });
      return;
    }
    if (result.status === 404) {
      setSubmit({ kind: 'gone' });
      return;
    }
    setSubmit({ kind: 'failed' });
  };

  return (
    <div className={styles.surface}>
      <h2 className={styles.surfaceHeading}>Your order</h2>
      <ul className={styles.cartLines}>
        {cart.lines.map((line, index) => {
          const problems = lineProblems(index);
          return (
            <li
              key={`${line.item_id}-${String(index)}`}
              className={`${styles.cartLine} ${
                problems.length > 0 ? styles.staleLine : ''
              }`}
            >
              <p className={styles.cartLineHeader}>
                <span className={styles.cartLineName}>{line.name}</span>
                <span>{formatMinorUnits(lineTotalMinor(line), currency)}</span>
              </p>
              {line.options.length === 0 ? null : (
                <p className={styles.cartLineMeta}>
                  {line.options.map((option) => option.option_name).join(', ')}
                </p>
              )}
              {line.item_instructions === null ? null : (
                <p className={styles.cartLineMeta}>
                  “{line.item_instructions}”
                </p>
              )}
              {problems.map((problem) => (
                <p key={problem.reason} className={styles.problem}>
                  {PROBLEM_TEXT[problem.reason] ??
                    'This line can no longer be ordered as chosen.'}
                </p>
              ))}
              <div className={styles.cartLineControls}>
                <button
                  type="button"
                  className={styles.quantityButton}
                  aria-label={`Decrease quantity of ${line.name}`}
                  disabled={line.quantity <= 1}
                  onClick={() => {
                    updateCart(setLineQuantity(cart, index, line.quantity - 1));
                  }}
                >
                  −
                </button>
                <span className={styles.quantityValue}>{line.quantity}</span>
                <button
                  type="button"
                  className={styles.quantityButton}
                  aria-label={`Increase quantity of ${line.name}`}
                  disabled={line.quantity >= MAX_LINE_QUANTITY}
                  onClick={() => {
                    updateCart(setLineQuantity(cart, index, line.quantity + 1));
                  }}
                >
                  +
                </button>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={() => {
                    updateCart(removeLine(cart, index));
                  }}
                >
                  Remove {line.name}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {cartProblems.map((problem) => (
        <p key={problem.reason} className={styles.problem}>
          {PROBLEM_TEXT[problem.reason] ??
            'The menu changed while you were ordering — review your order.'}
        </p>
      ))}
      <p className={styles.totalRow}>
        <span>Total{submit.kind === 'price-changed' ? ' (updated)' : ''}</span>
        <span>{formatMinorUnits(displayTotalMinor, currency)}</span>
      </p>

      <label className={styles.fieldLabel} htmlFor="checkout-name">
        Name
      </label>
      <input
        id="checkout-name"
        className={styles.textInput}
        maxLength={MAX_NAME}
        autoComplete="name"
        value={name}
        onChange={(event) => {
          setName(event.target.value);
          invalidateKey();
        }}
      />
      {fieldErrors['name'] === undefined ? null : (
        <p className={styles.fieldError}>{fieldErrors['name']}</p>
      )}

      <label className={styles.fieldLabel} htmlFor="checkout-phone">
        Phone
      </label>
      <input
        id="checkout-phone"
        className={styles.textInput}
        maxLength={MAX_PHONE}
        type="tel"
        autoComplete="tel"
        value={phone}
        onChange={(event) => {
          setPhone(event.target.value);
          invalidateKey();
        }}
      />
      {fieldErrors['phone'] === undefined ? null : (
        <p className={styles.fieldError}>{fieldErrors['phone']}</p>
      )}

      <label className={styles.fieldLabel} htmlFor="checkout-email">
        Email (optional)
      </label>
      <input
        id="checkout-email"
        className={styles.textInput}
        maxLength={MAX_EMAIL}
        type="email"
        autoComplete="email"
        value={email}
        onChange={(event) => {
          setEmail(event.target.value);
          invalidateKey();
        }}
      />

      <label className={styles.fieldLabel} htmlFor="checkout-instructions">
        Order instructions (optional)
      </label>
      <textarea
        id="checkout-instructions"
        className={styles.textArea}
        maxLength={MAX_ORDER_INSTRUCTIONS}
        value={instructions}
        onChange={(event) => {
          setInstructions(event.target.value);
          invalidateKey();
        }}
      />

      <fieldset className={styles.pickupChoice}>
        <legend className={styles.fieldLabel}>Pickup time</legend>
        {asapEnabled ? (
          <label className={styles.optionRow}>
            <input
              type="radio"
              name="pickup-kind"
              checked={pickupKind === 'asap'}
              onChange={() => {
                setPickupKind('asap');
                invalidateKey();
              }}
            />
            <span>As soon as possible</span>
          </label>
        ) : null}
        <label className={styles.optionRow}>
          <input
            type="radio"
            name="pickup-kind"
            checked={pickupKind === 'scheduled'}
            onChange={() => {
              setPickupKind('scheduled');
              invalidateKey();
            }}
          />
          <span>Schedule for later</span>
        </label>
        {pickupKind === 'scheduled' ? (
          slots === null ? (
            <p className={styles.emptyState}>Loading pickup times…</p>
          ) : slots.length === 0 ? (
            <p className={styles.emptyState}>
              No scheduled pickup times are available right now.
            </p>
          ) : (
            <>
              <label className={styles.fieldLabel} htmlFor="checkout-slot">
                Choose a time
              </label>
              <select
                id="checkout-slot"
                className={styles.textInput}
                value={slot}
                onChange={(event) => {
                  setSlot(event.target.value);
                  invalidateKey();
                }}
              >
                <option value="">Select…</option>
                {slots.map((instant) => (
                  <option key={instant} value={instant}>
                    {formatInstant(instant, timezone)}
                  </option>
                ))}
              </select>
              {fieldErrors['slot'] === undefined ? null : (
                <p className={styles.fieldError}>{fieldErrors['slot']}</p>
              )}
            </>
          )
        ) : null}
      </fieldset>

      <label className={styles.consentRow}>
        <input
          type="checkbox"
          checked={consentUpdates}
          onChange={(event) => {
            setConsentUpdates(event.target.checked);
            invalidateKey();
          }}
        />
        <span>
          The restaurant may contact me with updates about this order.
        </span>
      </label>
      <label className={styles.consentRow}>
        <input
          type="checkbox"
          checked={consentMarketing}
          onChange={(event) => {
            setConsentMarketing(event.target.checked);
            invalidateKey();
          }}
        />
        <span>I would like to receive occasional news and offers.</span>
      </label>

      {submit.kind === 'price-changed' ? (
        <p className={styles.problem}>
          Prices changed while you were ordering: the total is now{' '}
          {formatMinorUnits(submit.totalMinor, currency)} (was{' '}
          {formatMinorUnits(submit.expectedMinor, currency)}). Individual line
          prices shown may be out of date — review your order, then place it
          again at the updated total.
        </p>
      ) : null}
      {submit.kind === 'stale' ? (
        <p className={styles.problem}>
          The menu changed while you were ordering — the marked lines need
          attention before placing.
        </p>
      ) : null}
      {submit.kind === 'slot-unavailable' ? (
        <p className={styles.problem}>
          That pickup time is no longer available — choose another.
        </p>
      ) : null}
      {submit.kind === 'key-reused' ? (
        <p className={styles.problem}>
          Something went out of sync — review your order and place it again.
        </p>
      ) : null}
      {submit.kind === 'paused' ? (
        <p className={styles.problem}>
          Ordering was just paused
          {submit.resumeAt === null
            ? '.'
            : ` — back around ${formatInstant(submit.resumeAt, timezone)}.`}
          {submit.note === null ? '' : ` “${submit.note}”`} Your order is saved;
          try again once ordering resumes.
        </p>
      ) : null}
      {submit.kind === 'gone' ? (
        <p className={styles.problem}>
          Online ordering is not available right now.{' '}
          <a href="/" className={styles.inlineLink}>
            Back to the storefront
          </a>
        </p>
      ) : null}
      {submit.kind === 'failed' ? (
        <p className={styles.problem}>
          Your order could not be placed — check your connection and try again.
          If you retry, you will not be charged twice or create a duplicate
          order.
        </p>
      ) : null}

      <button
        type="button"
        className={styles.primaryButton}
        disabled={submit.kind === 'submitting'}
        onClick={() => {
          void handleSubmit();
        }}
      >
        {submit.kind === 'submitting'
          ? 'Placing order…'
          : `Place order · ${formatMinorUnits(displayTotalMinor, currency)}`}
      </button>
    </div>
  );
}
