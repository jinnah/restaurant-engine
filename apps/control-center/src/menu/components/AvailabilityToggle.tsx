import { useState } from 'react';
import type { ItemSummary } from '@restaurant-engine/api-client';
import { asApiFailure } from '../../api/failure';
import { useNotify } from '../../components/NotificationProvider';
import { useSetItemAvailability } from '../menuData';
import styles from '../menu.module.css';

/**
 * The "sold out today" toggle.
 *
 * A separate workflow command with its own capability
 * (`business.catalog.availability`), which is why staff can operate it while
 * everything else on the page is closed to them — marking an item unavailable
 * is exactly the job the blueprint gives them (§2.2). It is deliberately not
 * part of the item PATCH contract (ruling D4), and it is independent of
 * hidden: a sold-out item stays listed publicly, a hidden one does not.
 *
 * `aria-pressed` rather than a checkbox: this is a command that takes effect
 * immediately, not a form field awaiting a save.
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

  return (
    <div className={styles.availability}>
      <button
        type="button"
        className={styles.quiet}
        aria-pressed={!item.is_available}
        disabled={setAvailability.isPending}
        onClick={() => {
          setError(null);
          setAvailability.mutate(
            { itemId: item.id, isAvailable: !item.is_available },
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
        {item.is_available ? 'Mark sold out' : 'Mark available'}
      </button>
      <span className={styles.availabilityState}>
        {item.is_available ? 'Available' : 'Sold out today'}
      </span>
      {error !== null && (
        <span role="alert" className={styles.fieldErrorText}>
          {error}
        </span>
      )}
    </div>
  );
}
