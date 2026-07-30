import { useState } from 'react';
import { Link } from 'react-router';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { formatDateTime } from './format';
import { storefrontPermissions } from './permissions';
import { HISTORY_PAGE_SIZE, useVersionsPage } from './storefrontData';
import styles from './storefront.module.css';

/**
 * Publication history: the current published version plus archived
 * versions, newest first (D-2). The draft is deliberately absent — its
 * only read surface is the overview.
 */
export function StorefrontHistoryPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const session = useSession();
  const [offset, setOffset] = useState(0);
  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;
  const permissions =
    membership === null ? null : storefrontPermissions(membership);
  const canRead = permissions?.canRead ?? false;

  const page = useVersionsPage(businessId, offset);

  if (membership === null) {
    return null; // The guard owns this case.
  }
  if (!canRead) {
    return (
      <section aria-labelledby="history-title">
        <h2 id="history-title">Storefront history</h2>
        <p className={styles.empty}>
          Storefront management is available to owners and managers. Your role
          does not include it.
        </p>
      </section>
    );
  }

  if (page.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading history…
      </p>
    );
  }
  if (page.isError) {
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>The history could not be loaded.</p>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void page.refetch();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const { items, total } = page.data;
  const hasPrevious = offset > 0;
  const hasNext = offset + HISTORY_PAGE_SIZE < total;

  return (
    <section aria-labelledby="history-title">
      <div className={styles.pageHead}>
        <h2 id="history-title">Storefront history</h2>
        <Link
          to={`/businesses/${businessId}/storefront`}
          className={styles.secondary}
        >
          Back to storefront
        </Link>
      </div>

      {total === 0 ? (
        <p className={styles.empty}>
          Nothing has been published yet. Versions appear here after your first
          publication.
        </p>
      ) : (
        <>
          <ul className={styles.historyList}>
            {items.map((version) => (
              <li key={version.id} className={styles.historyRow}>
                <div>
                  <Link
                    to={`/businesses/${businessId}/storefront/history/${version.id}`}
                  >
                    Version {version.version_number}
                  </Link>{' '}
                  <span
                    className={
                      version.state === 'published'
                        ? `${styles.stateBadge} ${styles.statePublished}`
                        : styles.stateBadge
                    }
                  >
                    {version.state === 'published' ? 'Published' : 'Archived'}
                  </span>
                </div>
                <span className={styles.historyMeta}>
                  {formatDateTime(version.published_at)} —{' '}
                  {version.design_variant}
                </span>
              </li>
            ))}
          </ul>
          <div className={styles.pager}>
            <button
              type="button"
              className={styles.secondary}
              disabled={!hasPrevious}
              onClick={() => {
                setOffset(Math.max(0, offset - HISTORY_PAGE_SIZE));
              }}
            >
              Newer
            </button>
            <span aria-live="polite">
              Showing {offset + 1}–{Math.min(offset + HISTORY_PAGE_SIZE, total)}{' '}
              of {total}
            </span>
            <button
              type="button"
              className={styles.secondary}
              disabled={!hasNext}
              onClick={() => {
                setOffset(offset + HISTORY_PAGE_SIZE);
              }}
            >
              Older
            </button>
          </div>
        </>
      )}
    </section>
  );
}
