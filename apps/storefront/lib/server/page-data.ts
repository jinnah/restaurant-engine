// Shared page-level data assembly (ADR-021): both public routes gate on
// the published storefront (no published version → no public site at all,
// one neutral 404 for every cause), and compose the public menu where the
// page needs it. `notFound()` is thrown here for the neutral cases;
// anything else unrenderable throws to the generic error boundary.

import { notFound } from 'next/navigation';

import type { PublicMenu } from '@restaurant-engine/api-client';

import type { PublicStorefront } from '../contract';
import type { MenuSectionData } from '../../components/sections/MenuSection';
import {
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
