import { useState } from 'react';
import type {
  FulfillmentOut,
  FulfillmentSet,
  HoursSettings,
} from '@restaurant-engine/api-client';
import { CheckboxField, FormField } from '../../components/FormField';
import type { FormFailure } from '../../components/formErrors';
import { useNotify } from '../../components/NotificationProvider';
import { ErrorSummary } from '../../components/StatusPanels';
import { hoursFailure, useSetFulfillment } from '../hoursData';
import styles from '../hours.module.css';

/** The numeric policy bounds (backend `hours.policies`, mirrored). */
const BOUNDS = {
  lead_time_minutes: { min: 0, max: 1440 },
  slot_interval_minutes: { min: 5, max: 120 },
  last_order_before_close_minutes: { min: 0, max: 240 },
  max_days_ahead: { min: 0, max: 30 },
} as const;

type NumericKey = keyof typeof BOUNDS;

// The D3 throttle (ADR-026, delivered M6D): nullable — empty means no
// cap. Bounds mirror the backend CHECK (1–100).
const THROTTLE_BOUNDS = { min: 1, max: 100 } as const;

interface FormState {
  pickupEnabled: boolean;
  asapEnabled: boolean;
  numbers: Record<NumericKey, string>;
  /** Empty string means unlimited (stored NULL). */
  maxOrdersPerSlot: string;
}

function stateFromSettings(fulfillment: FulfillmentOut): FormState {
  return {
    pickupEnabled: fulfillment.pickup_enabled,
    asapEnabled: fulfillment.asap_enabled,
    numbers: {
      lead_time_minutes: String(fulfillment.lead_time_minutes),
      slot_interval_minutes: String(fulfillment.slot_interval_minutes),
      last_order_before_close_minutes: String(
        fulfillment.last_order_before_close_minutes,
      ),
      max_days_ahead: String(fulfillment.max_days_ahead),
    },
    maxOrdersPerSlot:
      fulfillment.max_orders_per_slot === null
        ? ''
        : String(fulfillment.max_orders_per_slot),
  };
}

/** The throttle's save-blocking problem, or null. Empty is unlimited. */
function throttleError(value: string): string | null {
  if (value.trim() === '') {
    return null;
  }
  const parsed = Number(value);
  if (
    !Number.isInteger(parsed) ||
    parsed < THROTTLE_BOUNDS.min ||
    parsed > THROTTLE_BOUNDS.max
  ) {
    return `Use a whole number between ${String(THROTTLE_BOUNDS.min)} and ${String(THROTTLE_BOUNDS.max)}, or leave it empty for no cap.`;
  }
  return null;
}

/** The field's save-blocking problem, or null. Never blocks typing. */
function numberError(key: NumericKey, value: string): string | null {
  const bounds = BOUNDS[key];
  const parsed = Number(value);
  if (value.trim() === '' || !Number.isInteger(parsed)) {
    return `Enter a whole number between ${String(bounds.min)} and ${String(bounds.max)}.`;
  }
  if (parsed < bounds.min || parsed > bounds.max) {
    return `Use a value between ${String(bounds.min)} and ${String(bounds.max)}.`;
  }
  return null;
}

interface FulfillmentPanelProps {
  businessId: string;
  settings: HoursSettings;
  canEdit: boolean;
}

/**
 * The complete pickup policy as one full-document form (partial updates
 * would reintroduce the lost-update shape the convention avoids). When no
 * row exists yet (`is_configured === false`) the values shown are the
 * platform defaults, said plainly — the first save materializes them.
 * The D3 per-slot throttle (ADR-026, M6D) is the nullable exception:
 * empty means no cap, and the full document always says which.
 */
export function FulfillmentPanel({
  businessId,
  settings,
  canEdit,
}: FulfillmentPanelProps) {
  const notify = useNotify();
  const setFulfillment = useSetFulfillment(businessId);
  const [form, setForm] = useState<FormState>(() =>
    stateFromSettings(settings.fulfillment),
  );
  const [baseline, setBaseline] = useState<FormState>(() =>
    stateFromSettings(settings.fulfillment),
  );
  const [failure, setFailure] = useState<FormFailure | null>(null);

  if (!canEdit) {
    const fulfillment = settings.fulfillment;
    return (
      <section aria-labelledby="fulfillment-title" className={styles.panel}>
        <h3 id="fulfillment-title">Pickup and fulfillment</h3>
        {!fulfillment.is_configured && (
          <p className={styles.mutedText}>
            These are the platform defaults; nothing has been saved for this
            business yet.
          </p>
        )}
        <dl className={styles.statusList}>
          <dt>Pickup</dt>
          <dd>{fulfillment.pickup_enabled ? 'Enabled' : 'Disabled'}</dd>
          <dt>ASAP orders</dt>
          <dd>{fulfillment.asap_enabled ? 'Enabled' : 'Disabled'}</dd>
          <dt>Lead time</dt>
          <dd>{fulfillment.lead_time_minutes} minutes</dd>
          <dt>Slot interval</dt>
          <dd>{fulfillment.slot_interval_minutes} minutes</dd>
          <dt>Last order before close</dt>
          <dd>{fulfillment.last_order_before_close_minutes} minutes</dd>
          <dt>Orders ahead</dt>
          <dd>{fulfillment.max_days_ahead} days</dd>
          <dt>Orders per slot</dt>
          <dd>
            {fulfillment.max_orders_per_slot === null
              ? 'No cap'
              : fulfillment.max_orders_per_slot}
          </dd>
        </dl>
      </section>
    );
  }

  const errors: Record<NumericKey, string | null> = {
    lead_time_minutes: numberError(
      'lead_time_minutes',
      form.numbers.lead_time_minutes,
    ),
    slot_interval_minutes: numberError(
      'slot_interval_minutes',
      form.numbers.slot_interval_minutes,
    ),
    last_order_before_close_minutes: numberError(
      'last_order_before_close_minutes',
      form.numbers.last_order_before_close_minutes,
    ),
    max_days_ahead: numberError('max_days_ahead', form.numbers.max_days_ahead),
  };
  const throttleProblem = throttleError(form.maxOrdersPerSlot);
  const invalid =
    Object.values(errors).some((error) => error !== null) ||
    throttleProblem !== null;
  const dirty = JSON.stringify(form) !== JSON.stringify(baseline);
  const pending = setFulfillment.isPending;

  function setNumber(key: NumericKey, value: string) {
    setForm((current) => ({
      ...current,
      numbers: { ...current.numbers, [key]: value },
    }));
  }

  function save() {
    if (pending) {
      return;
    }
    setFailure(null);
    const body: FulfillmentSet = {
      pickup_enabled: form.pickupEnabled,
      asap_enabled: form.asapEnabled,
      lead_time_minutes: Number(form.numbers.lead_time_minutes),
      slot_interval_minutes: Number(form.numbers.slot_interval_minutes),
      last_order_before_close_minutes: Number(
        form.numbers.last_order_before_close_minutes,
      ),
      max_days_ahead: Number(form.numbers.max_days_ahead),
      max_orders_per_slot:
        form.maxOrdersPerSlot.trim() === ''
          ? null
          : Number(form.maxOrdersPerSlot),
    };
    setFulfillment.mutate(body, {
      onSuccess: (saved) => {
        // The baseline becomes the server-normalized result, pristine.
        setForm(stateFromSettings(saved.fulfillment));
        setBaseline(stateFromSettings(saved.fulfillment));
        notify({ message: 'Fulfillment settings saved.' });
      },
      onError: (error: unknown) => {
        setFailure(
          hoursFailure(error, 'The fulfillment settings could not be saved.'),
        );
      },
    });
  }

  return (
    <section aria-labelledby="fulfillment-title" className={styles.panel}>
      <h3 id="fulfillment-title">Pickup and fulfillment</h3>
      {failure !== null && <ErrorSummary failure={failure} />}
      {!settings.fulfillment.is_configured && (
        <p className={styles.mutedText}>
          These are the platform defaults — nothing has been saved for this
          business yet. Saving stores these values as your own.
        </p>
      )}
      <CheckboxField
        id="fulfillment-pickup"
        label="Pickup enabled"
        hint="Whether customers can place pickup orders at all."
        checked={form.pickupEnabled}
        disabled={pending}
        onChange={(event) => {
          setForm((current) => ({
            ...current,
            pickupEnabled: event.target.checked,
          }));
        }}
      />
      <CheckboxField
        id="fulfillment-asap"
        label="ASAP orders enabled"
        hint="Offer an as-soon-as-possible pickup time in addition to scheduled slots."
        checked={form.asapEnabled}
        disabled={pending}
        onChange={(event) => {
          setForm((current) => ({
            ...current,
            asapEnabled: event.target.checked,
          }));
        }}
      />
      <FormField
        id="fulfillment-lead-time"
        name="lead_time_minutes"
        label="Lead time (minutes)"
        hint="How long the kitchen needs between an order and its pickup time."
        type="number"
        min={BOUNDS.lead_time_minutes.min}
        max={BOUNDS.lead_time_minutes.max}
        value={form.numbers.lead_time_minutes}
        disabled={pending}
        error={errors.lead_time_minutes ?? undefined}
        onChange={(event) => {
          setNumber('lead_time_minutes', event.target.value);
        }}
      />
      <FormField
        id="fulfillment-slot-interval"
        name="slot_interval_minutes"
        label="Slot interval (minutes)"
        hint="How far apart pickup slots are offered."
        type="number"
        min={BOUNDS.slot_interval_minutes.min}
        max={BOUNDS.slot_interval_minutes.max}
        value={form.numbers.slot_interval_minutes}
        disabled={pending}
        error={errors.slot_interval_minutes ?? undefined}
        onChange={(event) => {
          setNumber('slot_interval_minutes', event.target.value);
        }}
      />
      <FormField
        id="fulfillment-last-order"
        name="last_order_before_close_minutes"
        label="Last order before close (minutes)"
        hint="Stop offering pickup times this close to closing."
        type="number"
        min={BOUNDS.last_order_before_close_minutes.min}
        max={BOUNDS.last_order_before_close_minutes.max}
        value={form.numbers.last_order_before_close_minutes}
        disabled={pending}
        error={errors.last_order_before_close_minutes ?? undefined}
        onChange={(event) => {
          setNumber('last_order_before_close_minutes', event.target.value);
        }}
      />
      <FormField
        id="fulfillment-days-ahead"
        name="max_days_ahead"
        label="Orders ahead (days)"
        hint="How many days in advance a pickup can be scheduled; 0 means same-day only."
        type="number"
        min={BOUNDS.max_days_ahead.min}
        max={BOUNDS.max_days_ahead.max}
        value={form.numbers.max_days_ahead}
        disabled={pending}
        error={errors.max_days_ahead ?? undefined}
        onChange={(event) => {
          setNumber('max_days_ahead', event.target.value);
        }}
      />
      <FormField
        id="fulfillment-orders-per-slot"
        name="max_orders_per_slot"
        label="Orders per slot"
        hint="Refuse a pickup time once this many orders already share it. Leave empty for no cap."
        type="number"
        min={THROTTLE_BOUNDS.min}
        max={THROTTLE_BOUNDS.max}
        value={form.maxOrdersPerSlot}
        disabled={pending}
        error={throttleProblem ?? undefined}
        onChange={(event) => {
          setForm((current) => ({
            ...current,
            maxOrdersPerSlot: event.target.value,
          }));
        }}
      />
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.submit}
          disabled={pending || !dirty || invalid}
          onClick={save}
        >
          {pending ? 'Saving…' : 'Save fulfillment settings'}
        </button>
        {dirty && !pending && (
          <span className={styles.mutedText} role="status">
            You have unsaved changes.
          </span>
        )}
      </div>
    </section>
  );
}
