import { useEffect } from 'react';
import { NavLink, Outlet } from 'react-router';
import { useSession } from '../auth/useSession';
import { findMembership, useCurrentBusinessId } from './useCurrentBusinessId';
import styles from './workspace.module.css';

/** Plain-language explanation of a lifecycle state that changes what you can do. */
function statusNote(status: string): string | null {
  switch (status) {
    case 'closed':
      return 'This business is closed. Its menu is kept for the record and can no longer be edited.';
    case 'suspended':
      return 'This business is suspended, so its storefront is offline. You can still edit the menu.';
    case 'provisioning':
      return 'This business is not live yet. You can build the menu now and it will be ready when it opens.';
    default:
      return null;
  }
}

/**
 * Chrome for one business's workspace: the business name, the section
 * navigation, and the lifecycle note when the state changes what the user
 * can do. Renders under RequireBusinessMembership, so a membership exists.
 *
 * M3E registers exactly one section. Storefront, hours, orders, and team
 * arrive in later milestones and slot into the same navigation.
 */
export function BusinessWorkspaceLayout() {
  const session = useSession();
  const businessId = useCurrentBusinessId();
  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;

  useEffect(() => {
    if (membership !== null) {
      document.title = `${membership.business_name} — Restaurant Engine`;
    }
  }, [membership]);

  if (membership === null) {
    return null; // The guard owns this case.
  }

  const note = statusNote(membership.business_status);

  return (
    <section aria-labelledby="workspace-title" className={styles.area}>
      <h1 id="workspace-title">{membership.business_name}</h1>
      <nav aria-label="Workspace sections" className={styles.nav}>
        <NavLink
          to={`/businesses/${membership.business_id}/menu`}
          className={({ isActive }) =>
            isActive ? styles.linkActive : styles.link
          }
        >
          Menu
        </NavLink>
      </nav>
      {note !== null && (
        <p className={styles.note}>
          <strong>{membership.business_status}</strong> — {note}
        </p>
      )}
      <Outlet />
    </section>
  );
}
