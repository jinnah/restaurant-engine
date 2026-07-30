import type { CSSProperties } from 'react';

import { accentForeground, safeAccent } from '../../accent';
import { siteLinkHref } from '../../links';
import type { VariantLayoutProps } from '../registry';
import styles from './classic.module.css';

// The `classic` variant layout (ADR-021): tenant-branded chrome around the
// shared section renderers. The page is entirely the tenant's — the
// business name is the h1 and every section heading is an h2, one fixed
// hierarchy regardless of section order. The tenant accent enters CSS as
// one custom property pair (`--accent` plus its computed black/white
// foreground), never as arbitrary styling. Chrome labels ("Menu") are
// neutral product copy; no platform branding appears.
export function ClassicLayout({
  storefront,
  children,
  links = 'active',
}: VariantLayoutProps) {
  const accent = safeAccent(storefront.theme.accent);
  const themeStyle = {
    '--accent': accent,
    '--accent-contrast': accentForeground(accent),
  } as CSSProperties;
  return (
    <div className={styles.page} style={themeStyle}>
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
