import type { ApiFailure } from '../api/failure';

/**
 * Nested 422 mapping for the full-document draft PUT (ADR-022 §7).
 *
 * The verified grammar (probed against the real backend model): the
 * envelope joins Pydantic locations with dots, FastAPI prefixes `body`,
 * and the discriminated-union TAG appears after the section index —
 *
 *     body.config.sections.0.hero.props.heading
 *     body.config.sections.2.gallery.props.images.0.alt_text
 *
 * Conversion: strip `body.config.`, verify the tag equals the form's
 * `sections[i].type`, drop the tag segment. Matching is by full indexed
 * path — never by field name — so repeated names (`heading`, `alt_text`)
 * cannot land on the wrong section. Anything unmappable (whole-document
 * paths, media-reference messages, a tag/index mismatch) stays in the
 * persistent form-level summary with the server's message verbatim.
 *
 * The theme is mapped by **exact published path only** (M4G-C). A Pydantic
 * field error naming `body.config.theme.palette`, `…type_pairing`,
 * `…logo`, or `…logo.media_id` reaches the control that owns it. The
 * service-level media rejection — unknown, cross-business, or non-image
 * references — is deliberately *not* one of these: it is a general 422
 * carrying `details.media_ids` and no field error at all, so it stays in
 * the summary with the server's own wording. Guessing a control from a
 * media id would mean inferring which reference the server refused, and
 * the response is indistinguishable by design (ADR-020 §10).
 */
export interface MappedFieldError {
  /** RHF path on ComposerValues, e.g. `sections.2.props.heading`. */
  path: string;
  message: string;
}

export interface MappedSaveFailure {
  fields: MappedFieldError[];
  /** Messages that could not be attached to a specific input. */
  unmapped: string[];
}

/**
 * `body.config.theme.…` suffixes the composer owns a control for, mapped
 * to their form paths. Exhaustive over the published `Theme` fields; a
 * suffix absent here stays in the summary rather than being guessed.
 */
const THEME_FIELD_PATHS: Record<string, string> = {
  accent: 'accent',
  palette: 'palette',
  type_pairing: 'typePairing',
  logo: 'logo',
  'logo.media_id': 'logo',
};

export function mapDraftSaveFailure(
  failure: ApiFailure,
  sectionTypes: readonly string[],
): MappedSaveFailure {
  const fields: MappedFieldError[] = [];
  const unmapped: string[] = [];
  const fieldErrors = failure.envelope?.error.field_errors ?? [];

  if (fieldErrors.length === 0) {
    const message = failure.envelope?.error.message;
    return { fields: [], unmapped: message === undefined ? [] : [message] };
  }

  for (const fieldError of fieldErrors) {
    const parts = fieldError.field.split('.');
    // body.config.theme.{suffix} → the brand control that owns it.
    if (parts[0] === 'body' && parts[1] === 'config' && parts[2] === 'theme') {
      const mapped = THEME_FIELD_PATHS[parts.slice(3).join('.')];
      if (mapped !== undefined) {
        fields.push({ path: mapped, message: fieldError.message });
        continue;
      }
    }
    // body.config.sections.{i}.{tag}.{rest...}
    if (
      parts.length >= 6 &&
      parts[0] === 'body' &&
      parts[1] === 'config' &&
      parts[2] === 'sections'
    ) {
      const index = Number(parts[3]);
      const tag = parts[4];
      if (
        Number.isInteger(index) &&
        index >= 0 &&
        sectionTypes[index] === tag
      ) {
        fields.push({
          path: `sections.${String(index)}.${parts.slice(5).join('.')}`,
          message: fieldError.message,
        });
        continue;
      }
    }
    unmapped.push(fieldError.message);
  }
  return { fields, unmapped };
}

/**
 * Relative section paths (`props.heading`, `props.images.3.alt_text`) →
 * the section dialog's field names. Unmappable paths return null and stay
 * on the card/summary level.
 */
export function dialogFieldFor(relativePath: string): string | null {
  const direct: Record<string, string> = {
    enabled: 'enabled',
    'props.heading': 'heading',
    'props.subheading': 'subheading',
    'props.primary_action': 'primaryAction',
    'props.intro': 'intro',
    'props.body': 'body',
    'props.show_open_now': 'showOpenNow',
    'props.phone': 'phone',
    'props.email': 'email',
    'props.image.media_id': 'image',
    'props.image.alt_text': 'image',
    'props.image': 'image',
  };
  const mapped = direct[relativePath];
  if (mapped !== undefined) {
    return mapped;
  }
  const addressLine = /^props\.address_lines\.(\d+)$/.exec(relativePath);
  if (addressLine !== null) {
    return `addressLines.${addressLine[1] ?? '0'}.value`;
  }
  const galleryImage = /^props\.images\.(\d+)(?:\.(media_id|alt_text))?$/.exec(
    relativePath,
  );
  if (galleryImage !== null) {
    return `images.${galleryImage[1] ?? '0'}`;
  }
  if (relativePath === 'props.address_lines') {
    return 'addressLines';
  }
  if (relativePath === 'props.images') {
    return 'images';
  }
  return null;
}
