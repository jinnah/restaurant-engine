import { Link } from 'react-router';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { formatDateTime } from './format';
import { storefrontPermissions } from './permissions';
import { useStorefrontOverview, useVersionDetail } from './storefrontData';
import styles from './storefront.module.css';

/**
 * The storefront overview: the honest factual status of the draft and the
 * published version (ADR-022 §9) — only facts the server states, never a
 * derived "edited since publish" or draft-versus-published equality
 * claim. The draft composer renders below this status panel.
 */
export function StorefrontOverviewPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const session = useSession();
  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;
  const permissions =
    membership === null ? null : storefrontPermissions(membership);
  const canRead = permissions?.canRead ?? false;

  const overview = useStorefrontOverview(businessId, canRead);
  const draft = overview.data?.draft ?? null;
  const published = overview.data?.published ?? null;

  // Provenance (ADR-022 §9): stated only when the server supports it. A
  // source equal to the current published row is the publication seed;
  // any other source is an archived version, resolved for its number.
  const sourceId = draft?.source_version_id ?? null;
  const restoredFrom = useVersionDetail(
    businessId,
    sourceId ?? '',
    canRead && sourceId !== null && sourceId !== (published?.id ?? null),
  );

  if (membership === null) {
    return null; // The guard owns this case.
  }
  if (!canRead) {
    // Staff hold no storefront read capability (ADR-020 §7): the
    // navigation never offers this page, and a deep link gets the honest
    // explanation the API would answer with — without a doomed request.
    return (
      <section aria-labelledby="storefront-title">
        <h2 id="storefront-title">Storefront</h2>
        <p className={styles.empty}>
          Storefront management is available to owners and managers. Your role
          does not include it.
        </p>
      </section>
    );
  }

  if (overview.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading storefront…
      </p>
    );
  }
  if (overview.isError) {
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>The storefront could not be loaded.</p>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void overview.refetch();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const provenance = (() => {
    if (draft === null || sourceId === null) {
      return null;
    }
    if (published !== null && sourceId === published.id) {
      return `This draft started from published version ${String(published.version_number)}.`;
    }
    if (restoredFrom.data !== undefined) {
      return `This draft was restored from version ${String(restoredFrom.data.version_number)}.`;
    }
    return null; // Unresolvable provenance is omitted, never guessed.
  })();

  return (
    <section aria-labelledby="storefront-title">
      <div className={styles.pageHead}>
        <h2 id="storefront-title">Storefront</h2>
        <div className={styles.actions}>
          <Link
            to={`/businesses/${businessId}/storefront/preview`}
            className={styles.secondary}
          >
            Preview
          </Link>
          <Link
            to={`/businesses/${businessId}/storefront/history`}
            className={styles.secondary}
          >
            History
          </Link>
        </div>
      </div>

      <div className={styles.panel}>
        <h3>Status</h3>
        <dl className={styles.statusList}>
          <dt>Draft</dt>
          <dd>
            {draft === null
              ? 'No draft yet'
              : `Last saved ${formatDateTime(draft.updated_at)}`}
          </dd>
          <dt>Published</dt>
          <dd>
            {published === null
              ? 'Never published'
              : `Version ${String(published.version_number)} — ${formatDateTime(published.published_at)}`}
          </dd>
          {draft !== null && (
            <>
              <dt>Design</dt>
              <dd>{draft.design_variant}</dd>
            </>
          )}
        </dl>
        {provenance !== null && <p className={styles.note}>{provenance}</p>}
        {draft === null && published === null && (
          <p className={styles.note}>
            Your storefront has not been set up yet. Saving a first draft
            creates it; nothing is public until you publish.
          </p>
        )}
        {permissions?.isReadOnly === true && (
          <p className={styles.note}>
            This business is closed, so the storefront is read-only. Its drafts
            and history are kept for the record.
          </p>
        )}
        {draft !== null && (
          <details className={styles.diagnostics}>
            <summary>Diagnostics</summary>
            <p>
              Draft lock version {String(draft.lock_version)} — created{' '}
              {formatDateTime(draft.created_at)}.
            </p>
          </details>
        )}
      </div>
    </section>
  );
}
