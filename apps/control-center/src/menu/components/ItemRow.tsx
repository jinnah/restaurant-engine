import type { ReactNode } from 'react';
import { Link } from 'react-router';
import type {
  ItemSummary,
  MediaAssetView,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../../api/ClientProvider';
import { formatMinor } from '../money';
import { StatusChips } from './StatusChips';
import styles from '../menu.module.css';

const THUMB_PX = 56;

/**
 * The smallest stored rendition wide enough for the thumbnail, falling back
 * to the canonical.
 *
 * Variants exist only where they are strictly narrower than the canonical
 * (ADR-017 R3/R4), so a small source image may have none at all — asking for
 * `w320` unconditionally would 404. Admin preview is `no-store` by the M3C
 * security ruling, so every mount re-fetches; picking the smallest adequate
 * rendition is what keeps that affordable.
 */
export function thumbnailVariant(
  asset: MediaAssetView | undefined,
  cssWidth: number,
): 'canonical' | 'w320' | 'w640' | 'w1280' {
  if (asset === undefined) {
    return 'canonical';
  }
  const target = cssWidth * 2; // allow for a 2x display
  const fit = asset.variants
    .filter((variant) => variant.width >= target)
    .sort((a, b) => a.width - b.width)[0];
  return fit?.variant ?? 'canonical';
}

interface ItemRowProps {
  businessId: string;
  item: ItemSummary;
  /** The Business's currency — prices carry none of their own (ADR-017 D8). */
  currency: string;
  /** The item's image asset when it is known; thumbnails degrade without it. */
  asset?: MediaAssetView;
  /** Rendered after the price — availability toggle, row actions. */
  actions?: ReactNode;
}

export function ItemRow({
  businessId,
  item,
  currency,
  asset,
  actions,
}: ItemRowProps) {
  const client = useApiClient();
  const hasImage = item.image_media_id !== null;

  return (
    <li className={styles.itemRow}>
      {hasImage && item.image_media_id !== null ? (
        <img
          className={styles.thumb}
          src={client.media.fileUrl(
            businessId,
            item.image_media_id,
            thumbnailVariant(asset, THUMB_PX),
          )}
          // The item name is already the row's text; a decorative repeat
          // would just make a screen reader say it twice.
          alt={item.image_alt_text ?? ''}
          width={THUMB_PX}
          height={THUMB_PX}
          loading="lazy"
          decoding="async"
        />
      ) : (
        // Reserves the same box so a row never reflows when images load.
        <span className={styles.thumbPlaceholder} aria-hidden="true" />
      )}
      <div className={styles.itemMain}>
        <Link
          to={`/businesses/${businessId}/menu/items/${item.id}`}
          className={styles.itemName}
        >
          {item.name}
        </Link>
        <StatusChips item={item} />
      </div>
      <p className={styles.itemPrice}>
        {formatMinor(item.price_minor, currency)}
      </p>
      {actions}
    </li>
  );
}
