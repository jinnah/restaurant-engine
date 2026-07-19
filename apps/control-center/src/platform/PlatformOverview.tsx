import { useEffect } from 'react';
import { Link } from 'react-router';
import styles from './PlatformOverview.module.css';

/**
 * The /platform landing: a short orientation to the administration
 * areas. Entitlement administration is deliberately absent (ADR-016):
 * the platform API cannot read a business's current feature set, so a
 * write-only screen could silently revoke entitlements.
 */
export function PlatformOverview() {
  useEffect(() => {
    document.title = 'Platform — Restaurant Engine';
  }, []);

  return (
    <div>
      <p className={styles.lede}>
        Provision and manage businesses, issue account recovery, and review the
        platform audit trail.
      </p>
      <ul className={styles.cards}>
        <li className={styles.card}>
          <h2>
            <Link to="/platform/businesses">Businesses</Link>
          </h2>
          <p>Create businesses, manage their lifecycle, and invite owners.</p>
        </li>
        <li className={styles.card}>
          <h2>
            <Link to="/platform/recovery">Recovery</Link>
          </h2>
          <p>Issue single-use password-reset tokens for locked-out users.</p>
        </li>
        <li className={styles.card}>
          <h2>
            <Link to="/platform/audit">Audit</Link>
          </h2>
          <p>Review the platform-wide audit trail of recorded actions.</p>
        </li>
      </ul>
    </div>
  );
}
