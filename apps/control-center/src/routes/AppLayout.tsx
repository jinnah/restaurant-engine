import { Outlet } from 'react-router';
import { useLogout } from '../auth/useLogout';
import { useSession } from '../auth/useSession';
import styles from './AppLayout.module.css';

/**
 * Chrome for authenticated routes: who is signed in, and the way out.
 * Renders only under RequireAuth, so the session is authenticated here.
 */
export function AppLayout() {
  const session = useSession();
  const logout = useLogout();

  if (session.status !== 'authenticated') {
    // RequireAuth already handles every other state; render nothing
    // during the brief transition after logout clears the session.
    return null;
  }

  return (
    <>
      <div className={styles.bar}>
        <p className={styles.identity}>
          Signed in as <strong>{session.session.user.display_name}</strong>{' '}
          <span className={styles.email}>({session.session.user.email})</span>
        </p>
        <button
          type="button"
          className={styles.signOut}
          disabled={logout.isPending}
          onClick={() => {
            logout.mutate();
          }}
        >
          {logout.isPending ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
      {logout.isError && (
        <p role="alert" className={styles.logoutError}>
          Sign-out failed. Please try again.
        </p>
      )}
      <Outlet />
    </>
  );
}
