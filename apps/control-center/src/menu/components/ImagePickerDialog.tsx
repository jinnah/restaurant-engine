import {
  MediaLibraryDialog,
  type MediaLibraryDialogProps,
} from '../../media/MediaLibraryDialog';

/**
 * The menu item-image adapter over the shared media-selection primitive
 * (ADR-022 §4). The dialog's behavior — upload, library, pending honesty,
 * deletion, the describe/decorative alt choice — lives in
 * `media/MediaLibraryDialog`; this adapter carries exactly the M3E copy
 * (ADR-018 rulings 9 and 10), so the item flow reads precisely as it did
 * before the extraction.
 */
export function ImagePickerDialog(
  props: Omit<MediaLibraryDialogProps, 'copy'>,
) {
  return (
    <MediaLibraryDialog
      {...props}
      copy={{
        title: 'Choose an image',
        confirmLabel: 'Use for this item',
        pendingConfirmLabel: 'Saving…',
        decorativeLabel:
          'This image is decorative — it adds nothing beyond the item name',
        altHint: 'For example: Golden samosas stacked on a banana leaf.',
        deleteConflictMessage:
          'This image is still used by a menu item. Remove it from that item first.',
      }}
    />
  );
}
