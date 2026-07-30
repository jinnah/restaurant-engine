import type { PublicMenuItem } from '@restaurant-engine/api-client';

import type { PublicMenuSection } from '../../lib/contract';
import { formatMinorUnits } from '../../lib/money';
import { StorefrontImage } from '../StorefrontImage';
import menuStyles from '../menu/menu.module.css';
import styles from './sections.module.css';

// The menu section carries heading and intro only — which items appear,
// their order, and featured status are catalog's answer through the public
// menu projection (ADR-020 §2). The renderer composes the section with
// that projection: the centrally governed featured items (blueprint §12.1
// names featured items on the home page) plus navigation to the complete
// menu. Labels are product chrome.
export interface MenuSectionData {
  currency: string;
  featured: PublicMenuItem[];
}

export function MenuSection({
  section,
  menuData,
}: {
  section: PublicMenuSection;
  menuData: MenuSectionData | null;
}) {
  const { heading, intro } = section.props;
  const featured = menuData?.featured ?? [];
  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>{heading}</h2>
      {intro === null ? null : <p className={styles.intro}>{intro}</p>}
      {menuData === null || featured.length === 0 ? null : (
        <ul className={menuStyles.featuredGrid}>
          {featured.map((item) => (
            <li key={item.id} className={menuStyles.featuredCard}>
              {item.image === null ? null : (
                <StorefrontImage
                  image={item.image}
                  sizes="(max-width: 46rem) 100vw, 15rem"
                  loading="lazy"
                  className={menuStyles.featuredImage}
                />
              )}
              <p className={menuStyles.featuredBody}>
                <span className={menuStyles.itemName}>{item.name}</span>{' '}
                <span className={menuStyles.itemPrice}>
                  {formatMinorUnits(item.price_minor, menuData.currency)}
                </span>
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className={styles.menuLink}>
        <a href="/menu" className={styles.cta}>
          View the full menu
        </a>
      </p>
    </section>
  );
}
