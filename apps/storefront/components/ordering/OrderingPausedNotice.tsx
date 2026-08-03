// The paused ordering state (M7B, ADR-027 D8): a server-rendered,
// customer-visible explanation — never a vanished surface. No 'use
// client': there is nothing to hydrate; the owner's note and the
// optional resume instant are facts the server already has. The
// visitor's cart lives untouched in their browser, so resuming finds
// their order exactly where they left it.

import { formatInstant } from '../../lib/ordering/format';
import styles from './ordering.module.css';

export function OrderingPausedNotice({
  note,
  resumesAt,
  timezone,
}: {
  note: string | null;
  resumesAt: string | null;
  timezone: string;
}) {
  return (
    <div className={styles.surface}>
      <h2 className={styles.surfaceHeading}>Ordering is paused</h2>
      <p className={styles.emptyState}>
        Online ordering is temporarily paused
        {resumesAt === null
          ? '.'
          : ` — we expect to be back around ${formatInstant(resumesAt, timezone)}.`}
      </p>
      {note === null ? null : <p className={styles.problem}>{note}</p>}
      <p className={styles.emptyState}>
        Anything already in your order is saved and will be here when ordering
        resumes.{' '}
        <a href="/menu" className={styles.inlineLink}>
          Back to the menu
        </a>
      </p>
    </div>
  );
}
