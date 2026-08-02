// Shared page-level data assembly (ADR-021): both public routes gate on
// the published storefront (no published version → no public site at all,
// one neutral 404 for every cause), and compose the public menu where the
// page needs it. `notFound()` is thrown here for the neutral cases;
// anything else unrenderable throws to the generic error boundary.

import { notFound } from 'next/navigation';

import type {
  PublicAvailability,
  PublicMenu,
} from '@restaurant-engine/api-client';
import type {
  HoursSectionData,
  MenuSectionData,
  PublicStorefront,
} from '@restaurant-engine/storefront-renderer';

import {
  getPublicAvailability,
  getPublicMenu,
  getPublishedStorefront,
  type StorefrontResult,
} from './storefront-data';

function unwrap<T>(result: StorefrontResult<T>): T {
  if (result.kind === 'not-found') {
    notFound();
  }
  if (result.kind === 'unavailable') {
    throw new Error('storefront backend unavailable');
  }
  return result.data;
}

export async function requirePublishedStorefront(): Promise<PublicStorefront> {
  return unwrap(await getPublishedStorefront());
}

export async function requirePublicMenu(): Promise<PublicMenu> {
  return unwrap(await getPublicMenu());
}

export async function requirePublicAvailability(): Promise<PublicAvailability> {
  return unwrap(await getPublicAvailability());
}

/**
 * The hours section's render-time composition (M5D, ADR-025 D5): the
 * slice of the availability projection the renderer presents. Field
 * names stay the contract's; the tenant timezone rides along so the
 * instant facts are always formatted in the tenant's zone, never the
 * server's.
 */
export function hoursSectionData(
  availability: PublicAvailability,
): HoursSectionData {
  return {
    timezone: availability.business.timezone,
    is_open_now: availability.is_open_now,
    closes_at: availability.closes_at,
    next_opens_at: availability.next_opens_at,
    weekly: availability.weekly,
    exceptions: availability.exceptions,
  };
}

/** Featured items in the projection's featured order, for the menu section. */
export function menuSectionData(menu: PublicMenu): MenuSectionData {
  const itemsById = new Map(
    menu.categories.flatMap((category) =>
      category.items.map((item) => [item.id, item] as const),
    ),
  );
  return {
    currency: menu.business.currency,
    featured: menu.featured_item_ids
      .map((id) => itemsById.get(id))
      .filter((item) => item !== undefined),
  };
}
