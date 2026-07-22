import { useState } from 'react';
import styles from '../menu.module.css';
import { moveDown, moveTo, moveUp, sameOrder } from '../reorder';

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
 * Move up, Move down, and an explicit position field are the whole
 * mechanism, not a fallback behind a drag handle (ADR-018 ruling 5). Drag
 * would need a dependency or a hand-written pointer system, would still
 * require exactly this as its accessible alternative, and would still have
 * to compute the same permutation — so it buys nothing here.
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
        Use the buttons to change the order, then save. Nothing changes until
        you do.
      </p>
      <ol className={styles.reorderList}>
        {order.map((entry, index) => (
          <li key={entry.id} className={styles.reorderRow}>
            <span className={styles.reorderPosition}>{index + 1}</span>
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
              Up
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
              Down
            </button>
            <label
              className={styles.positionField}
              htmlFor={`position-${entry.id}`}
            >
              <span className={styles.visuallyHidden}>
                Position for {entry.name}
              </span>
              <input
                id={`position-${entry.id}`}
                type="number"
                min={1}
                max={order.length}
                value={index + 1}
                disabled={pending}
                onChange={(event) => {
                  const target = Number(event.target.value) - 1;
                  if (Number.isInteger(target)) {
                    apply(moveTo(order, index, target), entry);
                  }
                }}
              />
            </label>
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
