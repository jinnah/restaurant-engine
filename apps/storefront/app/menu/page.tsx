import type { Metadata } from 'next';

import { MenuListing } from '../../components/menu/MenuListing';
import { VariantLayout } from '../../components/variants/registry';
import {
  requirePublicMenu,
  requirePublishedStorefront,
} from '../../lib/server/page-data';
import { storefrontMetadata } from '../../lib/server/page-metadata';

// The complete public menu under the tenant's published chrome (ADR-021).
// The route is gated on the published storefront exactly like `/`: the
// design variant and theme live only on the published version, so a
// business that has never published has no public site — and no menu
// page — under any route. One neutral 404 for every ineligible case.
export const dynamic = 'force-dynamic';

export function generateMetadata(): Promise<Metadata> {
  return storefrontMetadata('menu');
}

export default async function MenuPage() {
  const storefront = await requirePublishedStorefront();
  const menu = await requirePublicMenu();
  return (
    <VariantLayout storefront={storefront}>
      <MenuListing menu={menu} />
    </VariantLayout>
  );
}
