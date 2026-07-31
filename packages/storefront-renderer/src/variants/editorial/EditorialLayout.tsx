import { siteLinkHref } from '../../links';
import { ThemeLogo } from '../../theme/ThemeLogo';
import type { VariantLayoutProps } from '../registry';
import styles from './editorial.module.css';

// The `editorial` variant layout (M4G-B, ADR-024 §1/§8): premium
// typography, larger imagery, and a more spacious composition, with a
// centred masthead of its own.
//
// It shares every section renderer with the other variants — there is no
// editorial fork of hero, menu, story, gallery, or contact. Its
// distinctness comes from three permitted sources only: its own chrome
// (this component), the tokens its root sets (the spacing scale and
// measure below), and CSS scoped under that root. The theme's palette,
// pairing, and accent tokens are applied once at the tenant-page
// boundary and simply inherit here.
//
// The accessibility floors are identical to every other variant: the four
// landmarks, the business name as the single visible `h1` with the logo
// beside it, and 44px navigation targets.
export function EditorialLayout({
  storefront,
  children,
  links = 'active',
}: VariantLayoutProps) {
  return (
    <div className={styles.page} data-variant="editorial" data-motion="rich">
      <header className={styles.header}>
        <div className={styles.masthead}>
          {storefront.theme.logo === null ? null : (
            <ThemeLogo
              logo={storefront.theme.logo}
              sizes="14rem"
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
