import type {
  DraftPut,
  PaletteId,
  StorefrontConfig,
  Theme,
  ThemeLogo,
  TypePairingId,
} from '@restaurant-engine/api-client';

/** One section of the administrative composition (the config shape). */
export type ConfigSection = NonNullable<StorefrontConfig['sections']>[number];
export type SectionType = ConfigSection['type'];

/**
 * The theme of the loaded draft, carried verbatim through an edit.
 *
 * The draft PUT is a **full-document replacement** (ADR-020 D-5), so any
 * theme field the composer does not re-send is reset to its schema default
 * by the next ordinary save. M4G-C added the palette, typography-pairing,
 * and logo controls beside the delivered accent, so those four fields are
 * now edited rather than carried — but the carry stays, because it is what
 * preserves a theme field the contract may add *next*: a future additive
 * field survives an unrelated heading edit the moment it is published,
 * with no change here.
 *
 * The whole theme is carried and the edited fields are layered on top at
 * serialization, rather than the untouched fields being enumerated.
 * `theme.accent`, `theme.palette`, `theme.type_pairing`, and `theme.logo`
 * inside this value are the *loaded* values and are always superseded —
 * {@link toDraftPut} is the single place that resolves the two.
 */
export type CarriedTheme = Theme;

/** The backend's default accent token (storefront.policies.DEFAULT_ACCENT). */
export const DEFAULT_ACCENT = '#a34b2a';

/**
 * The backend's default palette and typography pairing
 * (`storefront.theme_registries`, ADR-024 §3).
 *
 * Mirrored for one narrow reason: the generated `Theme` type makes every
 * field carrying a schema default *required*, so the create path — which
 * has no stored configuration to carry — has to state them. All three
 * theme defaults are published by the committed OpenAPI document and are
 * pinned to it by a build-time test, the ADR-022 §7 mirror discipline, so
 * drift fails CI rather than silently overriding the server.
 *
 * These are the **first-use** values only. A loaded draft always shows its
 * own stored palette and pairing; nothing here ever overrides the server.
 */
export const DEFAULT_PALETTE: PaletteId = 'warm';
export const DEFAULT_TYPE_PAIRING: TypePairingId = 'humanist';

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
  'hours',
];

/**
 * The parent form's model (ADR-022 §4): the canonical config sections plus
 * the accent token. Sections hold contract-shaped values — the section
 * dialogs own the editable-string ↔ nullable conversions, so the parent
 * always serializes without reinterpretation.
 */
export interface ComposerValues {
  accent: string;
  /** The selected curated palette (ADR-024 §5) — a closed contract enum. */
  palette: PaletteId;
  /** The selected curated typography pairing (ADR-024 §6). */
  typePairing: TypePairingId;
  /**
   * The staged or stored tenant logo, or `null` for none.
   *
   * `ThemeLogo` carries a `media_id` and nothing else: the logo is
   * permanently decorative (ADR-024 §7), so there is no alt text to hold.
   * Selecting one only *stages* the reference here — the claim happens
   * server-side when the draft is saved (ADR-020 §10).
   */
  logo: ThemeLogo | null;
  /**
   * The loaded draft's theme, held in the form so it travels with the
   * editing baseline. Keeping it here rather than reading it from the
   * overview cache at save time is deliberate: the form is seeded once per
   * loaded draft and is structurally immune to background rebinding (§6),
   * and a conflict deliberately leaves the cache stale without refetching —
   * sourcing part of the payload from the cache would reintroduce exactly
   * the silent merge those rules forbid.
   */
  carriedTheme: CarriedTheme;
  sections: ConfigSection[];
}

/**
 * The loaded config's theme, or the platform defaults when composing the
 * very first draft (there is nothing stored to carry).
 */
export function carriedThemeFromConfig(
  config: StorefrontConfig | null,
): CarriedTheme {
  const theme = config?.theme;
  return theme === undefined
    ? {
        accent: DEFAULT_ACCENT,
        palette: DEFAULT_PALETTE,
        type_pairing: DEFAULT_TYPE_PAIRING,
      }
    : structuredClone(theme);
}

export function composerValuesFromConfig(
  config: StorefrontConfig | null,
): ComposerValues {
  const logo = config?.theme?.logo;
  return {
    accent: config?.theme?.accent ?? DEFAULT_ACCENT,
    palette: config?.theme?.palette ?? DEFAULT_PALETTE,
    typePairing: config?.theme?.type_pairing ?? DEFAULT_TYPE_PAIRING,
    // Cloned rather than shared: the source object belongs to the query
    // cache, and form state must never alias it.
    logo:
      logo === null || logo === undefined ? null : { media_id: logo.media_id },
    carriedTheme: carriedThemeFromConfig(config),
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
    // Carried fields first so every field the composer owns wins. A theme
    // field this form does not edit still round-trips from `carriedTheme`.
    theme: {
      ...values.carriedTheme,
      accent: values.accent,
      palette: values.palette,
      type_pairing: values.typePairing,
      logo: values.logo,
    },
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
    case 'hours':
      // Presentation choices only (ADR-025 D5): the schedule itself is
      // authored in the hours workspace and composed at render time.
      return {
        id: 'hours',
        type: 'hours',
        enabled: true,
        props: { heading: '', intro: null, show_open_now: true },
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
  hours: 'Hours',
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
