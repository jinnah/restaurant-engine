import styles from './platform.module.css';

/** Badge class for a business lifecycle status (M2B state machine). */
export function statusBadgeClass(status: string): string | undefined {
  if (status === 'active') {
    return styles.badgeActive;
  }
  if (status === 'closed') {
    return styles.badgeClosed;
  }
  return styles.badge;
}
