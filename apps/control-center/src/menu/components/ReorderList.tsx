import { useState } from 'react';
import styles from '../menu.module.css';
import { moveDown, moveUp, sameOrder } from '../reorder';

export interface ReorderEntry {
  id: string;
  name: string;
}

interface ReorderListProps {
  /** What is being ordered, for the announcements and labels. */
  noun: string;
  entries: ReorderEntry[];
  pending: boolean;
  error: string | null;
  onSave: (orderedIds: string[]) => void;
  onCancel: () => void;
}

/**
 * Reordering by keyboard, with no drag-and-drop anywhere.
 *
 * Move up and Move down are the whole mechanism, alongside a read-only
 * "Position N" indicator (item 5): one understandable control, not a button
 * pair competing with an editable position box that did the same job in a
 * second, more ambiguous way. Drag would need a dependency or a hand-written
 * pointer system, would still require exactly the buttons as its accessible
 * alternative, and would still have to compute the same permutation — so it
 * buys nothing here (ADR-018 ruling 5).
 *
 * Every move is announced politely, because a purely visual reorder is
 * invisible to someone who cannot see the list move.
 */
export function ReorderList({
  noun,
  entries,
  pending,
  error,
  onSave,
  onCancel,
}: ReorderListProps) {
  const [order, setOrder] = useState<ReorderEntry[]>(entries);
  const [announcement, setAnnouncement] = useState('');

  function apply(next: ReorderEntry[], moved: ReorderEntry) {
    setOrder(next);
    const position = next.findIndex((entry) => entry.id === moved.id) + 1;
    setAnnouncement(
      `${moved.name} moved to position ${String(position)} of ${String(next.length)}.`,
    );
  }

  const originalIds = entries.map((entry) => entry.id);
  const currentIds = order.map((entry) => entry.id);
  const unchanged = sameOrder(originalIds, currentIds);

  return (
    <div className={styles.reorder}>
      <p className={styles.reorderHint}>
        Use Move up and Move down to change the order, then save. Nothing
        changes until you do.
      </p>
      <ol className={styles.reorderList}>
        {order.map((entry, index) => (
          <li key={entry.id} className={styles.reorderRow}>
            {/* A read-only indicator, not an input: it reports where the entry
                sits, and the buttons are the only way to change it (item 5). */}
            <span className={styles.reorderPosition}>Position {index + 1}</span>
            <span className={styles.reorderName}>{entry.name}</span>
            <button
              type="button"
              className={styles.quiet}
              disabled={index === 0 || pending}
              aria-label={`Move ${entry.name} up`}
              onClick={() => {
                apply(moveUp(order, index), entry);
              }}
            >
              Move up
            </button>
            <button
              type="button"
              className={styles.quiet}
              disabled={index === order.length - 1 || pending}
              aria-label={`Move ${entry.name} down`}
              onClick={() => {
                apply(moveDown(order, index), entry);
              }}
            >
              Move down
            </button>
          </li>
        ))}
      </ol>

      <p role="status" className={styles.visuallyHidden}>
        {announcement}
      </p>
      {error !== null && (
        <p role="alert" className={styles.fieldErrorText}>
          {error}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.secondary}
          onClick={onCancel}
          disabled={pending}
        >
          Cancel
        </button>
        <button
          type="button"
          className={styles.submit}
          disabled={pending || unchanged}
          onClick={() => {
            // The complete permutation, always: the server validates the
            // submitted set against the stored one.
            onSave(currentIds);
          }}
        >
          {pending ? 'Saving…' : `Save ${noun} order`}
        </button>
      </div>
    </div>
  );
}
