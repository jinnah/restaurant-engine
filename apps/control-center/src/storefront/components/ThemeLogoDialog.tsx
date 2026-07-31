import {
  MediaLibraryDialog,
  type MediaLibraryDialogProps,
} from '../../media/MediaLibraryDialog';

/**
 * The theme-logo adapter over the shared media-selection primitive
 * (M4G-C, ADR-024 §7).
 *
 * Two things separate it from the section-image adapter beside it.
 *
 * It runs the primitive in **decorative mode**: the logo is permanently
 * decorative, so there is no describe/decorative choice and no
 * description field — `ThemeLogo` carries a `media_id` and nothing else,
 * and the renderer emits a literal `alt=""`. The business name stays the
 * visible heading in every variant, so a logo description would be a
 * second announcement of the same fact.
 *
 * Its footnote says what is true of a *logo*: the name is not replaced,
 * the choice is staged in the editor, the claim happens on save, and
 * publication is what makes anything public (ADR-020 §10).
 */
export function ThemeLogoDialog(
  props: Omit<MediaLibraryDialogProps, 'copy' | 'altMode'>,
) {
  return (
    <MediaLibraryDialog
      {...props}
      altMode="decorative"
      copy={{
        title: 'Choose a logo',
        confirmLabel: 'Use this logo',
        pendingConfirmLabel: 'Saving…',
        deleteConflictMessage:
          'This image is still in use, so it cannot be deleted.',
        footnote:
          'Your logo appears next to your business name, which is always shown as text — the logo never replaces it. Your choice is kept in the editor until you save the draft, and nothing becomes public until you publish.',
      }}
    />
  );
}
