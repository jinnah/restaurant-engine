import { useEffect, useRef, useState } from 'react';
import type { MediaAssetView } from '@restaurant-engine/api-client';
import { useApiClient } from '../../api/ClientProvider';
import { asApiFailure } from '../../api/failure';
import { classifyFailure } from '../../api/failures';
import { Dialog } from '../../components/Dialog';
import { TextAreaField } from '../../components/FormField';
import styles from '../menu.module.css';
import {
  ACCEPTED_IMAGE_TYPES,
  ADVISORY_MAX_BYTES,
  isUnsupportedType,
  MEDIA_PAGE_SIZE,
  useMediaPage,
  useUploadAsset,
} from '../mediaData';
import { UnsavedChangesPrompt } from './UnsavedChangesPrompt';

const MAX_ALT = 300;

/** How the alt text will be sent. Neither is preselected for a new choice. */
type AltChoice = 'describe' | 'decorative' | null;

interface Props {
  businessId: string;
  /** Preselected when replacing, so the current description is kept. */
  current: { assetId: string; altText: string | null } | null;
  onAttach: (assetId: string, altText: string | null) => void;
  onCancel: () => void;
  pending: boolean;
  error: string | null;
}

function formatBytes(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${String(Math.ceil(bytes / 1024))} KB`;
}

/**
 * Choose an image for a menu item: upload a new one, or pick from the
 * library, then describe it.
 *
 * Uploading and attaching are two different operations against two different
 * domains, and the dialog does them in that order rather than pretending they
 * are one. An upload that is never attached simply stays in the library and
 * expires on its own (48 hours, ADR-017 R7) — the library says so rather than
 * hiding it.
 *
 * Dismissal is governed by the *attach*, never by the upload. The client
 * exposes no abort signal, so closing the dialog does not cancel the request,
 * and blocking dismissal during one would remove the only keyboard exit from
 * a modal for the duration of a network call — a WCAG 2.1.2 keyboard trap —
 * while protecting nothing. So the dialog stays dismissable by both the
 * visible control and Escape while an upload runs.
 *
 * The notice is scoped precisely to what is actually true: closing this
 * dialog is survivable because the mutation outlives the component, but a
 * reload, a tab close, or navigating out of the app terminates the request
 * like any other in-flight fetch — so the promise is "continues while this
 * app remains open", not "cannot be cancelled". Nor is success promised:
 * the upload may still fail, so the library appearance is conditional.
 *
 * The attach is different: it is a short mutation whose result the dialog
 * reports, so it keeps the strict pending behaviour, as do the confirm and
 * lifecycle dialogs.
 */
export function ImagePickerDialog({
  businessId,
  current,
  onAttach,
  onCancel,
  pending,
  error,
}: Props) {
  const client = useApiClient();
  const [offset, setOffset] = useState(0);
  const library = useMediaPage(businessId, {
    limit: MEDIA_PAGE_SIZE,
    offset,
  });
  const upload = useUploadAsset(businessId);

  const [selected, setSelected] = useState<string | null>(
    current?.assetId ?? null,
  );
  const [altChoice, setAltChoice] = useState<AltChoice>(
    current === null
      ? null
      : current.altText === null
        ? 'decorative'
        : 'describe',
  );
  const [altText, setAltText] = useState(current?.altText ?? '');
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [advisory, setAdvisory] = useState<string | null>(null);

  // Selection controls are inert while either operation runs, so a second
  // upload cannot start and the choice cannot change under an in-flight
  // attach. Dismissal deliberately is NOT part of this.
  const uploading = upload.isPending;
  const busy = pending || uploading;

  const dismissRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (uploading) {
      // The file input is disabled the moment the upload starts, which drops
      // focus to <body> — outside this dialog's key handler, putting Escape
      // out of reach. Moving focus to the dismissal control keeps the exit
      // both reachable and obvious.
      dismissRef.current?.focus();
    }
  }, [uploading]);

  function chooseFile(file: File | undefined) {
    setFileError(null);
    setUploadError(null);
    setAdvisory(null);
    if (file === undefined) {
      return;
    }
    // Only a *stated* type that is definitely wrong is refused here. An
    // empty File.type is common on Android pickers for perfectly valid
    // images, so it goes to the server, which inspects the actual bytes.
    if (isUnsupportedType(file.type)) {
      setFileError('Choose a JPEG, PNG, or WebP image.');
      return;
    }
    if (file.size === 0) {
      setFileError('That file is empty.');
      return;
    }
    if (file.size > ADVISORY_MAX_BYTES) {
      setAdvisory(
        `This file is ${formatBytes(file.size)}, which may be larger than this server accepts. You can still try.`,
      );
    }
    upload.mutate(file, {
      onSuccess: (asset) => {
        setSelected(asset.id);
        if (altChoice === null) {
          setAltChoice(null);
        }
      },
      onError: (unknownError: unknown) => {
        const failure = asApiFailure(unknownError);
        const kind = classifyFailure(failure);
        setUploadError(
          kind === 'tooLarge'
            ? 'That file is larger than this server accepts. Try a smaller image.'
            : (failure.envelope?.error.message ??
                'That image could not be uploaded.'),
        );
      },
    });
  }

  const canConfirm =
    selected !== null &&
    altChoice !== null &&
    !(altChoice === 'describe' && altText.trim() === '') &&
    !busy;

  return (
    <Dialog title="Choose an image" pending={pending} onCancel={onCancel}>
      <div className={styles.field}>
        <label htmlFor="image-file">Upload a new image</label>
        <input
          id="image-file"
          type="file"
          accept={ACCEPTED_IMAGE_TYPES.join(',')}
          disabled={busy}
          onChange={(event) => {
            chooseFile(event.target.files?.[0]);
          }}
        />
        <p className={styles.fieldHintText}>
          JPEG, PNG, or WebP. The image is re-encoded and resized for you.
        </p>
      </div>

      {uploading && (
        <p role="status" className={styles.noticeText}>
          Uploading… You can close this dialog; the upload will continue in the
          background while this app remains open. When it succeeds, the image
          will appear in your library.
        </p>
      )}
      {advisory !== null && (
        <p role="status" className={styles.noticeText}>
          {advisory}
        </p>
      )}
      {fileError !== null && (
        <p role="alert" className={styles.fieldErrorText}>
          {fileError}
        </p>
      )}
      {uploadError !== null && (
        <p role="alert" className={styles.fieldErrorText}>
          {uploadError}
        </p>
      )}

      <h3 className={styles.libraryTitle}>Or choose from your library</h3>
      {library.isPending && (
        <p role="status" className={styles.loading}>
          Loading images…
        </p>
      )}
      {library.isError && (
        <p role="alert" className={styles.fieldErrorText}>
          Your image library could not be loaded.
        </p>
      )}
      {library.isSuccess && library.data.items.length === 0 && (
        <p className={styles.empty}>
          You have no images yet. Upload one above.
        </p>
      )}
      {library.isSuccess && library.data.items.length > 0 && (
        <>
          <ul className={styles.libraryGrid}>
            {library.data.items.map((asset: MediaAssetView) => (
              <li key={asset.id}>
                <button
                  type="button"
                  className={
                    selected === asset.id
                      ? styles.libraryTileSelected
                      : styles.libraryTile
                  }
                  aria-pressed={selected === asset.id}
                  disabled={busy}
                  onClick={() => {
                    setSelected(asset.id);
                  }}
                >
                  <img
                    src={client.media.fileUrl(
                      businessId,
                      asset.id,
                      'canonical',
                    )}
                    alt=""
                    width={96}
                    height={96}
                    loading="lazy"
                    decoding="async"
                  />
                  <span className={styles.libraryName}>
                    {asset.original_filename}
                  </span>
                  {asset.status === 'pending' &&
                    asset.pending_expires_at !== null && (
                      <span className={styles.libraryMeta}>
                        Not used yet — expires{' '}
                        {new Date(
                          asset.pending_expires_at,
                        ).toLocaleDateString()}
                      </span>
                    )}
                </button>
              </li>
            ))}
          </ul>
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.secondary}
              disabled={offset === 0 || busy}
              onClick={() => {
                setOffset(Math.max(0, offset - MEDIA_PAGE_SIZE));
              }}
            >
              Previous
            </button>
            <button
              type="button"
              className={styles.secondary}
              disabled={offset + MEDIA_PAGE_SIZE >= library.data.total || busy}
              onClick={() => {
                setOffset(offset + MEDIA_PAGE_SIZE);
              }}
            >
              Next
            </button>
          </div>
        </>
      )}

      {selected !== null && (
        <fieldset className={styles.fieldset}>
          <legend>Describe this image</legend>
          <p className={styles.fieldHintText}>
            People using a screen reader hear the description instead of the
            image.
          </p>
          <div className={styles.check}>
            <input
              id="alt-describe"
              type="radio"
              name="alt-choice"
              checked={altChoice === 'describe'}
              onChange={() => {
                setAltChoice('describe');
              }}
            />
            <label htmlFor="alt-describe">Describe this image</label>
          </div>
          {altChoice === 'describe' && (
            <TextAreaField
              id="alt-text"
              label="Description"
              hint="For example: Golden samosas stacked on a banana leaf."
              maxLength={MAX_ALT}
              value={altText}
              onChange={(event) => {
                setAltText(event.target.value);
              }}
            />
          )}
          <div className={styles.check}>
            <input
              id="alt-decorative"
              type="radio"
              name="alt-choice"
              checked={altChoice === 'decorative'}
              onChange={() => {
                setAltChoice('decorative');
              }}
            />
            <label htmlFor="alt-decorative">
              This image is decorative — it adds nothing beyond the item name
            </label>
          </div>
        </fieldset>
      )}

      {error !== null && (
        <p role="alert" className={styles.fieldErrorText}>
          {error}
        </p>
      )}

      <div className={styles.actions}>
        <button
          ref={dismissRef}
          type="button"
          className={styles.secondary}
          onClick={onCancel}
          // Only the attach blocks dismissal. "Close" rather than "Cancel"
          // while uploading, because nothing is cancelled by pressing it.
          disabled={pending}
        >
          {uploading ? 'Close' : 'Cancel'}
        </button>
        <button
          type="button"
          className={styles.submit}
          disabled={!canConfirm}
          onClick={() => {
            if (selected !== null) {
              // Blank normalizes to null server-side anyway; sending null for
              // the decorative branch makes the intent explicit.
              onAttach(
                selected,
                altChoice === 'describe' ? altText.trim() : null,
              );
            }
          }}
        >
          {pending ? 'Saving…' : 'Use for this item'}
        </button>
      </div>

      <UnsavedChangesPrompt
        when={uploading}
        // In-app navigation only; the browser owns the reload/close prompt.
        // Moving within the app keeps the upload alive, so that is all this
        // claims — not that the request is uncancellable.
        message="An image is still uploading. It will keep going while this app stays open."
      />
    </Dialog>
  );
}
