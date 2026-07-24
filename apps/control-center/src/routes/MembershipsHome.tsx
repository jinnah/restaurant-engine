import { useEffect } from 'react';
import { Link } from 'react-router';
import { useSession } from '../auth/useSession';
import styles from './MembershipsHome.module.css';

/**
 * The authenticated landing, presented for the role that reaches it (item 1).
 *
 * A restaurant owner arrives at their **Restaurant Dashboard** — the list of
 * restaurants they manage, each a way into that restaurant's workspace. A
 * platform administrator arrives at **Platform Administration**: they hold no
 * restaurant membership by architecture (ADR-011), so their landing points at
 * the platform area rather than pretending to be an owner's. One application,
 * two clearly different experiences — never duplicated screens.
 *
 * The switcher in the app bar is the fast path once you are inside a
 * restaurant; this is the map you start from.
 */
export function MembershipsHome() {
  const session = useSession();

  const isAdmin =
    session.status === 'authenticated' &&
    session.session.user.is_platform_admin;

  useEffect(() => {
    document.title =
      (isAdmin ? 'Platform Administration' : 'Restaurant Dashboard') +
      ' — Restaurant Engine';
  }, [isAdmin]);

  if (session.status !== 'authenticated') {
    return null; // RequireAuth owns every other state.
  }

  const memberships = session.session.memberships;

  return (
    <section aria-labelledby="home-title">
      <h1 id="home-title">
        {isAdmin ? 'Platform Administration' : 'Restaurant Dashboard'}
      </h1>

      {isAdmin && (
        <p className={styles.lede}>
          You manage restaurants across the platform. Onboard a restaurant,
          invite its owner, and control its lifecycle from{' '}
          <Link to="/platform">Platform Administration</Link>.
        </p>
      )}

      <h2>My restaurants</h2>
      {memberships.length === 0 ? (
        <p className={styles.empty}>
          {isAdmin
            ? 'You are not assigned to a specific restaurant. Manage every restaurant from Platform Administration above.'
            : "You don't manage any restaurants yet. They'll appear here once you're added to one."}
        </p>
      ) : (
        <ul className={styles.list}>
          {memberships.map((membership) => (
            <li key={membership.business_id} className={styles.item}>
              <Link
                to={`/businesses/${membership.business_id}/menu`}
                className={styles.name}
              >
                {membership.business_name}
              </Link>
              <span className={styles.meta}>
                <span className={styles.role}>{membership.role}</span>
                <span
                  className={
                    membership.business_status === 'active'
                      ? styles.statusActive
                      : styles.status
                  }
                >
                  {membership.business_status}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
