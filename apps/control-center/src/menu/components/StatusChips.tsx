import type { ItemSummary } from '@restaurant-engine/api-client';
import { dietaryLabel } from '../dietary';
import styles from '../menu.module.css';

/**
 * An item's states, as words.
 *
 * Every chip carries its own text, so nothing depends on colour being
 * perceived (blueprint §12.4). A visible, available, unfeatured item shows
 * no chip at all: absence is the signal for "normal", which keeps a long
 * menu readable instead of turning every row into a wall of badges.
 *
 * Hidden and sold out are separate states and are never merged
 * (ADR-017/docs/03) — a sold-out item is still listed publicly, a hidden one
 * is not.
 */
export function StatusChips({ item }: { item: ItemSummary }) {
  return (
    <span className={styles.chips}>
      {item.is_hidden && <span className={styles.chipHidden}>Hidden</span>}
      {!item.is_available && (
        <span className={styles.chipSoldOut}>Sold out</span>
      )}
      {item.is_featured && (
        <span className={styles.chipFeatured}>Featured</span>
      )}
      {item.dietary_tags.map((tag) => (
        <span key={tag} className={styles.chipDietary}>
          {dietaryLabel(tag)}
        </span>
      ))}
    </span>
  );
}
