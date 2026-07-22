import { useState } from 'react';
import type { ItemSummary } from '@restaurant-engine/api-client';
import { useApiClient } from '../../api/ClientProvider';
import { asApiFailure } from '../../api/failure';
import { classifyFailure } from '../../api/failures';
import { useNotify } from '../../components/NotificationProvider';
import { useSetItemImage } from '../menuData';
import { ImagePickerDialog } from './ImagePickerDialog';
import { thumbnailVariant } from './ItemRow';
import styles from '../menu.module.css';

const PREVIEW_PX = 160;

/**
 * The item's photo.
 *
 * Distinct operations with distinct labels, because they have distinct
 * consequences (ADR-018 ruling 10):
 *   Upload            — brings bytes into the business's library
 *   Use for this item  — points the item at an asset (and promotes it)
 *   Remove from item   — stops pointing; the asset survives
 *
 * Destroying an asset is the library's operation and lives in the picker,
 * not here. It was offered here, gated on the item still pointing at the
 * asset — which is exactly the state in which the backend must refuse it,
 * and following its own advice ("remove it from this item first") unmounted
 * the control before it could be used. Found by the M3F vertical slice; see
 * ADR-019.
 */
export function ItemImageSection({
  businessId,
  item,
  canWriteCatalog,
  canWriteMedia,
}: {
  businessId: string;
  item: ItemSummary;
  canWriteCatalog: boolean;
  canWriteMedia: boolean;
}) {
  const client = useApiClient();
  const notify = useNotify();
  const setImage = useSetItemImage(businessId);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assetId = item.image_media_id;

  function fail(fallback: string) {
    return (unknownError: unknown) => {
      const failure = asApiFailure(unknownError);
      const kind = classifyFailure(failure);
      if (kind === 'conflict') {
        setError(
          failure.envelope?.error.message ??
            'That image can no longer be used. It may have expired — upload it again.',
        );
        return;
      }
      if (kind === 'gone') {
        setError('That image is no longer available.');
        return;
      }
      setError(failure.envelope?.error.message ?? fallback);
    };
  }

  return (
    <section aria-labelledby="image-title" className={styles.imageSection}>
      <h3 id="image-title">Photo</h3>

      {error !== null && (
        <p role="alert" className={styles.fieldErrorText}>
          {error}
        </p>
      )}

      {assetId === null ? (
        <p className={styles.empty}>This item has no photo.</p>
      ) : (
        <img
          className={styles.preview}
          src={client.media.fileUrl(
            businessId,
            assetId,
            thumbnailVariant(undefined, PREVIEW_PX),
          )}
          alt={item.image_alt_text ?? ''}
          width={PREVIEW_PX}
          height={PREVIEW_PX}
          decoding="async"
        />
      )}

      {assetId !== null && item.image_alt_text === null && (
        <p className={styles.fieldHintText}>
          Marked decorative — screen readers will skip it.
        </p>
      )}

      {canWriteCatalog && (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              setError(null);
              setPicking(true);
            }}
          >
            {assetId === null ? 'Add a photo' : 'Replace photo'}
          </button>
          {assetId !== null && (
            <button
              type="button"
              className={styles.quiet}
              disabled={setImage.isPending}
              onClick={() => {
                setError(null);
                // Clearing sends media_id: null and no alt-text key at all —
                // alt text without an image is invalid by contract.
                setImage.mutate(
                  { itemId: item.id, body: { media_id: null } },
                  {
                    onSuccess: () => {
                      notify({ message: 'Photo removed from this item.' });
                    },
                    onError: fail('The photo could not be removed.'),
                  },
                );
              }}
            >
              Remove from item
            </button>
          )}
        </div>
      )}

      {picking && (
        <ImagePickerDialog
          businessId={businessId}
          canManageLibrary={canWriteMedia}
          current={
            assetId === null ? null : { assetId, altText: item.image_alt_text }
          }
          pending={setImage.isPending}
          error={null}
          onCancel={() => {
            setPicking(false);
          }}
          onAttach={(chosenId, altText) => {
            setError(null);
            setImage.mutate(
              {
                itemId: item.id,
                body: { media_id: chosenId, alt_text: altText },
              },
              {
                onSuccess: () => {
                  // Close first, then confirm: a notification published while
                  // the dialog is open would sit behind its focus trap.
                  setPicking(false);
                  notify({ message: 'Photo saved for this item.' });
                },
                onError: (unknownError: unknown) => {
                  setPicking(false);
                  fail('The photo could not be attached.')(unknownError);
                },
              },
            );
          }}
        />
      )}
    </section>
  );
}
