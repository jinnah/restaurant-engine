import type { StorefrontConfig } from '@restaurant-engine/api-client';

/** One section of the administrative composition (the config shape). */
export type ConfigSection = NonNullable<StorefrontConfig['sections']>[number];
export type SectionType = ConfigSection['type'];

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
