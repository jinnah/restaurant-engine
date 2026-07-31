import { Link } from 'react-router';
import {
  SectionList,
  tenantPageClass,
  themeStyle,
  VariantLayout,
} from '@restaurant-engine/storefront-renderer';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { storefrontPermissions } from './permissions';
import { useDraftPreview, useStorefrontOverview } from './storefrontData';
import styles from './storefront.module.css';

/**
 * The saved-draft preview (ADR-022 §3): the M4C render-equivalent
 * projection of the current SAVED draft, rendered through the SAME shared
 * renderer the public storefront uses — never a parallel preview
 * renderer — in `'inert'` link mode, so no navigation path exists and no
 * link role is announced. Media URLs are the authenticated relative
 * routes and resolve on this origin with the session cookie.
 */
export function StorefrontPreviewPage() {
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
  const preview = useDraftPreview(
    businessId,
    draft === null
      ? null
      : { lock_version: draft.lock_version, updated_at: draft.updated_at },
  );

  if (membership === null) {
    return null; // The guard owns this case.
  }
  if (!canRead) {
    return (
      <section aria-labelledby="preview-title">
        <h2 id="preview-title">Storefront preview</h2>
        <p className={styles.empty}>
          Storefront management is available to owners and managers. Your role
          does not include it.
        </p>
      </section>
    );
  }

  if (overview.isPending || (draft !== null && preview.isPending)) {
    return (
      <p role="status" className={styles.loading}>
        Loading preview…
      </p>
    );
  }
  if (overview.isError || preview.isError) {
    const retry = overview.isError ? overview.refetch : preview.refetch;
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>The preview could not be loaded.</p>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void retry();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  if (draft === null || preview.data === undefined) {
    return (
      <section aria-labelledby="preview-title">
        <h2 id="preview-title">Storefront preview</h2>
        <p className={styles.empty}>
          There is no draft to preview yet. Save a draft first.
        </p>
        <p>
          <Link
            to={`/businesses/${businessId}/storefront`}
            className={styles.secondary}
          >
            Back to storefront
          </Link>
        </p>
      </section>
    );
  }

  const projection = preview.data;
  const hasMenuSection = projection.sections.some(
    (section) => section.type === 'menu',
  );

  return (
    <section aria-labelledby="preview-title">
      <div className={styles.pageHead}>
        <h2 id="preview-title">Storefront preview</h2>
        <Link
          to={`/businesses/${businessId}/storefront`}
          className={styles.secondary}
        >
          Back to storefront
        </Link>
      </div>
      <div className={styles.panel}>
        <p className={styles.note}>
          This is a content preview of your last <strong>saved</strong> draft —
          unsaved edits are not shown. Links are disabled in this preview.
          Nothing here is public until you publish.
        </p>
        {hasMenuSection && (
          <p className={styles.note}>
            Featured menu items come from your live menu and appear on the
            published site; they are not shown in this preview.
          </p>
        )}
      </div>
      {/* The preview container is this app's `.tenantPage` element, so
          it carries the theme's custom properties exactly as the public
          <body> does (ADR-024 Section 5) - one typed source, identical
          public and preview rendering. */}
      <div
        className={`${styles.previewSurface} ${tenantPageClass}`}
        style={themeStyle(projection.theme)}
      >
        <VariantLayout storefront={projection} links="inert">
          <SectionList
            sections={projection.sections}
            menuData={null}
            links="inert"
          />
        </VariantLayout>
      </div>
    </section>
  );
}
