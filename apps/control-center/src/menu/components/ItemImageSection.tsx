import { useState } from 'react';
import type { ItemSummary } from '@restaurant-engine/api-client';
import { useApiClient } from '../../api/ClientProvider';
import { asApiFailure } from '../../api/failure';
import { classifyFailure } from '../../api/failures';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { useNotify } from '../../components/NotificationProvider';
import { useSetItemImage } from '../menuData';
import { useDeleteAsset } from '../mediaData';
import { ImagePickerDialog } from './ImagePickerDialog';
import { thumbnailVariant } from './ItemRow';
import styles from '../menu.module.css';

const PREVIEW_PX = 160;

/**
 * The item's photo.
 *
 * Four distinct operations with four distinct labels, because they have four
 * distinct consequences (ADR-018 ruling 10):
 *   Upload            — brings bytes into the business's library
 *   Use for this item  — points the item at an asset (and promotes it)
 *   Remove from item   — stops pointing; the asset survives
 *   Delete from library — destroys the asset, and only if nothing uses it
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
  const deleteAsset = useDeleteAsset(businessId);
  const [picking, setPicking] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
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
          {assetId !== null && canWriteMedia && (
            <button
              type="button"
              className={styles.quiet}
              onClick={() => {
                setError(null);
                setConfirmingDelete(true);
              }}
            >
              Delete from library
            </button>
          )}
        </div>
      )}

      {picking && (
        <ImagePickerDialog
          businessId={businessId}
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

      {confirmingDelete && assetId !== null && (
        <ConfirmDialog
          title="Delete this image from your library?"
          confirmLabel="Delete image"
          danger
          pending={deleteAsset.isPending}
          onCancel={() => {
            setConfirmingDelete(false);
          }}
          onConfirm={() => {
            deleteAsset.mutate(assetId, {
              onSuccess: () => {
                setConfirmingDelete(false);
                notify({ message: 'Image deleted.' });
              },
              onError: (unknownError: unknown) => {
                setConfirmingDelete(false);
                const failure = asApiFailure(unknownError);
                setError(
                  classifyFailure(failure) === 'conflict'
                    ? 'This image is still used by a menu item. Remove it from that item first.'
                    : (failure.envelope?.error.message ??
                        'The image could not be deleted.'),
                );
              },
            });
          }}
        >
          <p>
            This destroys the image permanently and cannot be undone. Remove it
            from this item first — an image still in use cannot be deleted.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}
