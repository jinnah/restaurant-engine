import type { PublicMenu, PublicMenuItem } from '@restaurant-engine/api-client';

import { formatMinorUnits } from '../../lib/money';
import { StorefrontImage } from '../StorefrontImage';
import styles from './menu.module.css';

// The complete browsable public menu (ADR-021), rendered exactly from the
// public menu projection: category and item order are the projection's
// array order, prices are exact minor-unit formatting, sold-out items stay
// listed ("sold out" and "hidden" are different states, docs/03), and
// dietary tags render as neutral labels. Deliberate M4D presentation
// boundaries: modifier groups and `is_orderable` are ordering-surface
// facts (M6) and are not rendered; there is no search. Badge and
// empty-state labels are product chrome.
const DIETARY_LABELS: Record<string, string> = {
  halal: 'Halal',
  vegetarian: 'Vegetarian',
  vegan: 'Vegan',
};

function dietaryLabel(tag: string): string {
  return DIETARY_LABELS[tag] ?? tag;
}

function MenuItem({
  item,
  currency,
  featured,
}: {
  item: PublicMenuItem;
  currency: string;
  featured: boolean;
}) {
  const badges = [
    ...(featured ? ['Featured'] : []),
    ...(item.is_available ? [] : ['Sold out']),
    ...item.dietary_tags.map(dietaryLabel),
  ];
  return (
    <li className={styles.item}>
      {item.image === null ? null : (
        <StorefrontImage
          image={item.image}
          sizes="72px"
          loading="lazy"
          className={styles.itemImage}
        />
      )}
      <div className={styles.itemBody}>
        <p className={styles.itemHeader}>
          <span className={styles.itemName}>{item.name}</span>
          <span className={styles.itemPrice}>
            {formatMinorUnits(item.price_minor, currency)}
          </span>
        </p>
        {item.description === null ? null : (
          <p className={styles.itemDescription}>{item.description}</p>
        )}
        {badges.length === 0 ? null : (
          <span className={styles.badges}>
            {badges.map((badge) => (
              <span
                key={badge}
                className={`${styles.badge} ${
                  badge === 'Featured'
                    ? styles.badgeFeatured
                    : badge === 'Sold out'
                      ? styles.badgeSoldOut
                      : ''
                }`}
              >
                {badge}
              </span>
            ))}
          </span>
        )}
      </div>
    </li>
  );
}

export function MenuListing({ menu }: { menu: PublicMenu }) {
  const featured = new Set(menu.featured_item_ids);
  return (
    <div className={styles.listing}>
      <h2 className={styles.pageHeading}>Menu</h2>
      {menu.categories.length === 0 ? (
        <p className={styles.empty}>No menu items are available right now.</p>
      ) : (
        menu.categories.map((category) => (
          <section key={category.id} className={styles.category}>
            <h3 className={styles.categoryName}>{category.name}</h3>
            {category.description === null ? null : (
              <p className={styles.categoryDescription}>
                {category.description}
              </p>
            )}
            <ul className={styles.items}>
              {category.items.map((item) => (
                <MenuItem
                  key={item.id}
                  item={item}
                  currency={menu.business.currency}
                  featured={featured.has(item.id)}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
