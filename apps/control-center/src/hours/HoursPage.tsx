import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { ExceptionsPanel } from './components/ExceptionsPanel';
import { FulfillmentPanel } from './components/FulfillmentPanel';
import { WeeklyHoursEditor } from './components/WeeklyHoursEditor';
import { useHoursSettings } from './hoursData';
import { hoursPermissions } from './permissions';
import styles from './hours.module.css';

/**
 * The hours workspace (M5C, ADR-025): the weekly schedule, date
 * exceptions, and fulfillment settings for one business. Every role can
 * read this page — hours reads ride on `business.view` (D7), staff see
 * the schedule they work — so unlike the storefront there is no
 * capability gate before the request. Writes are owner/manager and a
 * closed business refuses every mutation; both cases render read-only
 * with the reason said plainly.
 */
export function HoursPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const session = useSession();
  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;

  const settings = useHoursSettings(businessId);

  if (membership === null) {
    return null; // The guard owns this case.
  }
  const permissions = hoursPermissions(membership);

  if (settings.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading hours…
      </p>
    );
  }
  if (settings.isError) {
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>The hours could not be loaded.</p>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void settings.refetch();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <section aria-labelledby="hours-title">
      <h2 id="hours-title">Hours</h2>
      {/* The one fact every minute below depends on (ADR-025 D1: stored
          values are local wall time under exactly this zone). */}
      <p className={styles.timezoneLine}>
        All times are local to {settings.data.timezone}.
      </p>
      {permissions.readOnlyReason === 'closed' && (
        <p className={styles.note}>
          This business is closed. Its hours are kept for the record and can no
          longer be changed.
        </p>
      )}
      {permissions.readOnlyReason === 'role' && (
        <p className={styles.note}>
          You can view the schedule; only owners and managers can change it.
        </p>
      )}
      <WeeklyHoursEditor
        businessId={businessId}
        settings={settings.data}
        canEdit={permissions.canEdit}
      />
      <ExceptionsPanel
        businessId={businessId}
        settings={settings.data}
        canEdit={permissions.canEdit}
      />
      <FulfillmentPanel
        businessId={businessId}
        settings={settings.data}
        canEdit={permissions.canEdit}
      />
    </section>
  );
}
