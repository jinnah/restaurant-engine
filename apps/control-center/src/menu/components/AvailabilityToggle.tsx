import { useState } from 'react';
import type { ItemSummary } from '@restaurant-engine/api-client';
import { asApiFailure } from '../../api/failure';
import { useNotify } from '../../components/NotificationProvider';
import { useSetItemAvailability } from '../menuData';
import styles from '../menu.module.css';

/**
 * The availability control — one control, one status (item 7).
 *
 * A separate workflow command with its own capability
 * (`business.catalog.availability`), which is why staff can operate it while
 * everything else on the page is closed to them — marking an item unavailable
 * is exactly the job the blueprint gives them (§2.2). It is deliberately not
 * part of the item PATCH contract (ruling D4), and it is independent of
 * hidden: a sold-out item stays listed publicly, a hidden one does not.
 *
 * The single status word "Sold out" is shown only when there is a state to
 * report — an available item carries none, matching the item chips, so a menu
 * is not a wall of "Available" labels. The one control is a toggle button
 * whose label is the action it performs; `aria-pressed` conveys the state to
 * assistive technology, and the change takes effect immediately (no save).
 * The word carries the meaning, never colour alone (blueprint §12.4).
 */
export function AvailabilityToggle({
  businessId,
  item,
}: {
  businessId: string;
  item: ItemSummary;
}) {
  const setAvailability = useSetItemAvailability(businessId);
  const notify = useNotify();
  const [error, setError] = useState<string | null>(null);

  const soldOut = !item.is_available;

  return (
    <div className={styles.availability}>
      {soldOut && <span className={styles.soldOutStatus}>Sold out</span>}
      <button
        type="button"
        className={styles.quiet}
        aria-pressed={soldOut}
        disabled={setAvailability.isPending}
        onClick={() => {
          setError(null);
          setAvailability.mutate(
            { itemId: item.id, isAvailable: soldOut },
            {
              onSuccess: (updated) => {
                notify({
                  message: updated.is_available
                    ? `“${updated.name}” is available again.`
                    : `“${updated.name}” is marked sold out.`,
                });
              },
              onError: (unknownError: unknown) => {
                const failure = asApiFailure(unknownError);
                setError(
                  failure.envelope?.error.message ??
                    'That could not be changed just now.',
                );
              },
            },
          );
        }}
      >
        {soldOut ? 'Mark available' : 'Mark sold out'}
      </button>
      {error !== null && (
        <span role="alert" className={styles.fieldErrorText}>
          {error}
        </span>
      )}
    </div>
  );
}
