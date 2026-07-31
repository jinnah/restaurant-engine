import { siteLinkHref } from '../../links';
import type { VariantLayoutProps } from '../registry';
import styles from './classic.module.css';

// The `classic` variant layout (ADR-021): tenant-branded chrome around the
// shared section renderers. The page is entirely the tenant's — the
// business name is the h1 and every section heading is an h2, one fixed
// hierarchy regardless of section order. Chrome labels ("Menu") are
// neutral product copy; no platform branding appears.
//
// M4G-B (ADR-024 §5): the theme's custom properties — palette, typography
// pairing, and the accent pair — are no longer set here. They are applied
// once, by `themeStyle()`, on the element carrying `tenantPageClass`, so
// the painted browser canvas and every descendant read the same typed
// source. A variant sets only its own chrome tokens.
export function ClassicLayout({
  storefront,
  children,
  links = 'active',
}: VariantLayoutProps) {
  return (
    <div className={styles.page} data-variant="classic">
      <header className={styles.header}>
        <h1 className={styles.name}>{storefront.business.name}</h1>
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
