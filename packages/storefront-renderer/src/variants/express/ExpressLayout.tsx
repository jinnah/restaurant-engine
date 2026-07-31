import { siteLinkHref } from '../../links';
import { ThemeLogo } from '../../theme/ThemeLogo';
import type { VariantLayoutProps } from '../registry';
import styles from './express.module.css';

// The `express` variant layout (M4G-B, ADR-024 §1/§8): compact and
// action-oriented — denser spacing, a low-profile header, and the primary
// action given visual weight so the menu is the obvious next step.
//
// Like editorial it shares every section renderer and expresses itself
// only through its own chrome, its root tokens, and root-scoped CSS.
//
// **Express carries no motion at all** (ADR-024 §9, ruled): this file's
// stylesheet declares no animation, and the motion policy suite asserts
// that.
export function ExpressLayout({
  storefront,
  children,
  links = 'active',
}: VariantLayoutProps) {
  return (
    <div className={styles.page} data-variant="express" data-motion="none">
      <header className={styles.header}>
        <div className={styles.identity}>
          {storefront.theme.logo === null ? null : (
            <ThemeLogo
              logo={storefront.theme.logo}
              sizes="8rem"
              className={styles.logo}
            />
          )}
          <h1 className={styles.name}>{storefront.business.name}</h1>
        </div>
        <nav aria-label="Site" className={styles.nav}>
          <a href={siteLinkHref(links, '/menu')} className={styles.navLink}>
            Menu
          </a>
        </nav>
      </header>
      <main className={styles.main}>{children}</main>
      <footer className={styles.footer}>
        <p className={styles.footerName}>{storefront.business.name}</p>
      </footer>
    </div>
  );
}
