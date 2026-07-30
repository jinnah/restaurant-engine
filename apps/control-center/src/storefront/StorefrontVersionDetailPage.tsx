import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { asApiFailure } from '../api/failure';
import { classifyFailure } from '../api/failures';
import { RestoreVersionDialog } from './components/RestoreVersionDialog';
import { SECTION_TYPE_LABELS, sectionSummary } from './composition';
import { formatDateTime } from './format';
import { storefrontPermissions } from './permissions';
import { useVersionDetail } from './storefrontData';
import styles from './storefront.module.css';

/**
 * One published or archived version, read-only (D-2): metadata plus a
 * section-by-section content summary — the inspection surface a restore
 * decision is made from. The draft is never readable here; its id
 * answers the same 404 as an unknown one, and the UI preserves that
 * non-disclosure by rendering one neutral not-found state.
 */
export function StorefrontVersionDetailPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const { versionId = '' } = useParams();
  const session = useSession();
  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;
  const permissions =
    membership === null ? null : storefrontPermissions(membership);
  const canRead = permissions?.canRead ?? false;

  const detail = useVersionDetail(businessId, versionId, canRead);
  const [restoring, setRestoring] = useState(false);

  if (membership === null) {
    return null; // The guard owns this case.
  }
  if (!canRead) {
    return (
      <section aria-labelledby="version-title">
        <h2 id="version-title">Storefront version</h2>
        <p className={styles.empty}>
          Storefront management is available to owners and managers. Your role
          does not include it.
        </p>
      </section>
    );
  }

  if (detail.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading version…
      </p>
    );
  }
  if (detail.isError) {
    const kind = classifyFailure(asApiFailure(detail.error));
    if (kind === 'gone') {
      return (
        <section aria-labelledby="version-title">
          <h2 id="version-title">Storefront version</h2>
          <p className={styles.empty}>This version could not be found.</p>
          <p>
            <Link
              to={`/businesses/${businessId}/storefront/history`}
              className={styles.secondary}
            >
              Back to history
            </Link>
          </p>
        </section>
      );
    }
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>The version could not be loaded.</p>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void detail.refetch();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  const version = detail.data;
  const sections = version.config.sections ?? [];

  return (
    <section aria-labelledby="version-title">
      <div className={styles.pageHead}>
        <h2 id="version-title">
          Version {version.version_number}
          {version.state === 'published' ? ' (published)' : ' (archived)'}
        </h2>
        <Link
          to={`/businesses/${businessId}/storefront/history`}
          className={styles.secondary}
        >
          Back to history
        </Link>
      </div>

      <div className={styles.panel}>
        <dl className={styles.statusList}>
          <dt>Published</dt>
          <dd>{formatDateTime(version.published_at)}</dd>
          <dt>Design</dt>
          <dd>{version.design_variant}</dd>
        </dl>
        {/* Archived sources only (D-4); owner-only; closed businesses
            mutate nothing. The dialog itself fetches the fresh draft
            lock version when it opens (ADR-022 §8). */}
        {version.state === 'archived' && permissions?.canRestore === true && (
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => {
                setRestoring(true);
              }}
            >
              Restore this version to the draft
            </button>
          </div>
        )}
      </div>

      {restoring && (
        <RestoreVersionDialog
          businessId={businessId}
          versionId={versionId}
          versionNumber={version.version_number}
          onClose={() => {
            setRestoring(false);
          }}
        />
      )}

      <div className={styles.panel}>
        <h3>Sections</h3>
        {sections.length === 0 ? (
          <p className={styles.note}>
            This version has no sections — it renders the business name and
            navigation only.
          </p>
        ) : (
          <ul className={styles.sectionRows}>
            {sections.map((section) => {
              const summary = sectionSummary(section);
              return (
                <li key={section.id} className={styles.sectionRow}>
                  <div className={styles.sectionRowBody}>
                    <strong>{SECTION_TYPE_LABELS[section.type]}</strong>
                    {summary !== null && (
                      <div className={styles.sectionSummaryText}>{summary}</div>
                    )}
                  </div>
                  {!section.enabled && (
                    <span className={styles.disabledBadge}>Hidden</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
