import type { ItemSummary } from '@restaurant-engine/api-client';
import { dietaryLabel } from '../dietary';
import styles from '../menu.module.css';

/**
 * An item's states, as words.
 *
 * Every chip carries its own text, so nothing depends on colour being
 * perceived (blueprint §12.4). A visible, unfeatured item shows no chip at
 * all: absence is the signal for "normal", which keeps a long menu readable
 * instead of turning every row into a wall of badges.
 *
 * Sold-out is deliberately absent here: availability has one home now — the
 * availability control (item 7) — so it is not also shown as a chip. Hidden
 * and sold out remain separate states (ADR-017/docs/03); this component just
 * no longer duplicates the availability one.
 */
export function StatusChips({ item }: { item: ItemSummary }) {
  return (
    <span className={styles.chips}>
      {item.is_hidden && <span className={styles.chipHidden}>Hidden</span>}
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
