import {
  MediaLibraryDialog,
  type MediaLibraryDialogProps,
} from '../../media/MediaLibraryDialog';

/**
 * The storefront section-image adapter over the shared media-selection
 * primitive (ADR-022 §4). Selection here only STAGES `{media_id,
 * alt_text}` in the composer's form state: the claim happens when the
 * draft is saved (ADR-020 §10), and nothing becomes public until a
 * version referencing the image is published — the footnote states
 * exactly that and no more.
 */
export function StorefrontImageDialog(
  props: Omit<MediaLibraryDialogProps, 'copy'>,
) {
  return (
    <MediaLibraryDialog
      {...props}
      copy={{
        title: 'Choose an image',
        confirmLabel: 'Use this image',
        pendingConfirmLabel: 'Saving…',
        decorativeLabel:
          'This image is decorative — it adds nothing beyond the surrounding text',
        altHint: 'For example: The dining room set for dinner service.',
        deleteConflictMessage:
          'This image is still in use, so it cannot be deleted.',
        footnote:
          'Your choice is kept in the editor until you save the draft. A new upload stays in your library as "not used yet" until the draft is saved, and nothing becomes public until you publish.',
      }}
    />
  );
}
