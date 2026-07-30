import type { DraftPut, StorefrontConfig } from '@restaurant-engine/api-client';

/** One section of the administrative composition (the config shape). */
export type ConfigSection = NonNullable<StorefrontConfig['sections']>[number];
export type SectionType = ConfigSection['type'];

/** The backend's default accent token (storefront.policies.DEFAULT_ACCENT). */
export const DEFAULT_ACCENT = '#a34b2a';

/**
 * A staged section-image reference — the composer's normalized form of
 * the contract's `SectionImage` (whose `alt_text` may be absent): staging
 * always records the describe/decorative choice explicitly, and the shape
 * stays assignable to the contract field it serializes into.
 */
export interface SectionImageRef {
  media_id: string;
  alt_text: string | null;
}

/** Every registered section type, in the composer's offer order. */
export const SECTION_TYPES: readonly SectionType[] = [
  'hero',
  'menu',
  'story',
  'contact',
  'gallery',
];

/**
 * The parent form's model (ADR-022 §4): the canonical config sections plus
 * the accent token. Sections hold contract-shaped values — the section
 * dialogs own the editable-string ↔ nullable conversions, so the parent
 * always serializes without reinterpretation.
 */
export interface ComposerValues {
  accent: string;
  sections: ConfigSection[];
}

export function composerValuesFromConfig(
  config: StorefrontConfig | null,
): ComposerValues {
  return {
    accent: config?.theme?.accent ?? DEFAULT_ACCENT,
    sections: structuredClone(config?.sections ?? []),
  };
}

/**
 * Serialize the form into the full-document PUT (D-5). Create intent is
 * an OMITTED `expected_lock_version` (the "no draft exists" claim);
 * update intent is the saved draft's exact integer.
 */
export function toDraftPut(
  values: ComposerValues,
  expectedLockVersion: number | null,
): DraftPut {
  const config: StorefrontConfig = {
    schema_version: 1,
    theme: { accent: values.accent },
    sections: values.sections,
  };
  return expectedLockVersion === null
    ? { config }
    : { config, expected_lock_version: expectedLockVersion };
}

/**
 * The seed for a section being added (ADR-022 §4): `id` is the type name
 * — a valid slug, unique under the one-per-type invariant — and content
 * fields start empty for the owner to author. No placeholder copy is ever
 * fabricated. Existing sections round-trip their stored ids unchanged.
 */
export function defaultSectionValues(type: SectionType): ConfigSection {
  switch (type) {
    case 'hero':
      return {
        id: 'hero',
        type: 'hero',
        enabled: true,
        props: {
          heading: '',
          subheading: null,
          image: null,
          primary_action: 'none',
        },
      };
    case 'menu':
      return {
        id: 'menu',
        type: 'menu',
        enabled: true,
        props: { heading: '', intro: null },
      };
    case 'story':
      return {
        id: 'story',
        type: 'story',
        enabled: true,
        props: { heading: '', body: '' },
      };
    case 'contact':
      return {
        id: 'contact',
        type: 'contact',
        enabled: true,
        props: { heading: '', address_lines: [], phone: null, email: null },
      };
    case 'gallery':
      return {
        id: 'gallery',
        type: 'gallery',
        enabled: true,
        props: { heading: null, images: [] },
      };
  }
}

/**
 * Display-only labels backed by the generated union (ADR-004): a sixth
 * registered section type fails this Record's exhaustiveness at compile
 * time until the UI names it. Neutral English product chrome.
 */
export const SECTION_TYPE_LABELS: Record<SectionType, string> = {
  hero: 'Hero',
  menu: 'Menu',
  story: 'Story',
  contact: 'Contact',
  gallery: 'Gallery',
};

/**
 * A one-line owner-facing summary of a section's content: its heading
 * when it has one, rendered as text (never markup). Gallery headings are
 * optional; every other type requires one.
 */
export function sectionSummary(section: ConfigSection): string | null {
  const heading = section.props.heading;
  return heading === null || heading === undefined || heading === ''
    ? null
    : heading;
}
