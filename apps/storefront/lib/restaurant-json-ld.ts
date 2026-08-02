// Minimal, accurate Restaurant JSON-LD (ADR-021, extended by M5D): only
// supported facts — name, canonical URL, the enabled contact section's
// telephone and textual address, and the structured weekly hours from
// the availability projection (blueprint §12.2: hours are modeled, not
// decorative text). No cuisine, ordering, ratings, price range, or menu
// structured data: nothing is claimed that the platform does not model.
// Exceptions are deliberately not claimed: they are transient overrides
// with a bounded window, and a stale special-hours claim in a crawler's
// index would be less accurate than the weekly schedule alone.

import type { PublicAvailability } from '@restaurant-engine/api-client';
import type { PublicStorefront } from '@restaurant-engine/storefront-renderer';

// schema.org day names indexed by the contract's ISO day (0 = Monday).
const SCHEMA_DAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

/** A D1 minute value as the schema.org 24-hour wall time ("17:00"). */
function schemaTime(minute: number): string {
  const wrapped = minute % 1440;
  const hours = String(Math.floor(wrapped / 60)).padStart(2, '0');
  const minutes = String(wrapped % 60).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/**
 * The weekly schedule as OpeningHoursSpecification entries, one per
 * stored interval. A D1 overnight interval (`closes_minute` above 1440)
 * wraps to its wall time, which is schema.org's own overnight
 * convention: a `closes` earlier than `opens` spans into the following
 * day. The one degenerate case — a full 00:00–24:00 day, where the wrap
 * would make `closes` equal `opens` — is stated as 00:00–23:59, the
 * established encoding for "open all day".
 */
function openingHours(
  availability: PublicAvailability,
): Record<string, unknown>[] {
  return availability.weekly.map((interval) => {
    const opens = schemaTime(interval.opens_minute);
    let closes = schemaTime(interval.closes_minute);
    if (closes === opens) {
      closes = '23:59';
    }
    return {
      '@type': 'OpeningHoursSpecification',
      dayOfWeek: SCHEMA_DAYS[interval.day_of_week] ?? '',
      opens,
      closes,
    };
  });
}

export function restaurantJsonLd(
  storefront: PublicStorefront,
  origin: string | null,
  availability: PublicAvailability | null,
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
  // An empty schedule claims nothing: no key at all, never an empty
  // array pretending the hours are modeled.
  if (availability !== null && availability.weekly.length > 0) {
    data['openingHoursSpecification'] = openingHours(availability);
  }
  return data;
}
