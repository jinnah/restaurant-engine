import { NavLink, Outlet } from 'react-router';
import styles from './PlatformLayout.module.css';

const links = [
  { to: '/platform', label: 'Overview', end: true },
  { to: '/platform/businesses', label: 'Businesses', end: false },
  { to: '/platform/recovery', label: 'Recovery', end: false },
  { to: '/platform/audit', label: 'Audit', end: false },
];

/**
 * Chrome for the platform-administration area: heading plus a wrapping
 * sub-navigation that stays keyboard-operable and 44px-tall on narrow
 * screens. NavLink supplies aria-current="page" for the active section.
 */
export function PlatformLayout() {
  return (
    <section aria-labelledby="platform-title" className={styles.area}>
      <h1 id="platform-title">Platform administration</h1>
      <nav aria-label="Platform sections" className={styles.nav}>
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              isActive ? styles.linkActive : styles.link
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </section>
  );
}
