// Minimal, accurate Restaurant JSON-LD (ADR-021): only supported facts
// from the published projection — name, canonical URL, and the enabled
// contact section's telephone and textual address when present. No hours
// (M5), cuisine, ordering, ratings, price range, or menu structured data:
// nothing is claimed that the platform does not model.

import type { PublicStorefront } from '@restaurant-engine/storefront-renderer';

export function restaurantJsonLd(
  storefront: PublicStorefront,
  origin: string | null,
): Record<string, unknown> {
  const contact = storefront.sections.find(
    (section) => section.type === 'contact',
  );
  const data: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Restaurant',
    name: storefront.business.name,
  };
  if (origin !== null) {
    data['url'] = `${origin}/`;
  }
  if (contact !== undefined) {
    if (contact.props.phone !== null) {
      data['telephone'] = contact.props.phone;
    }
    if (contact.props.address_lines.length > 0) {
      data['address'] = contact.props.address_lines.join(', ');
    }
  }
  return data;
}
