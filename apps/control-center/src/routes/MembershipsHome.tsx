import { useEffect } from 'react';
import { Link } from 'react-router';
import { useSession } from '../auth/useSession';
import styles from './MembershipsHome.module.css';

/**
 * The authenticated landing: identity and the session's memberships, each a
 * way into that business's workspace (M3E). The switcher in the app bar is
 * the fast path once you are inside one; this is the map you start from.
 */
export function MembershipsHome() {
  const session = useSession();

  useEffect(() => {
    document.title = 'Control Center — Restaurant Engine';
  }, []);

  if (session.status !== 'authenticated') {
    return null; // RequireAuth owns every other state.
  }

  const { user } = session.session;
  const memberships = session.session.memberships;

  return (
    <section aria-labelledby="home-title">
      <h1 id="home-title">Control center</h1>
      {user.is_platform_admin && (
        <p className={styles.platformBadge}>Platform administrator</p>
      )}
      <h2>Your businesses</h2>
      {memberships.length === 0 ? (
        <p className={styles.empty}>
          You do not have any business memberships yet. Workspaces appear here
          once you join a business.
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
