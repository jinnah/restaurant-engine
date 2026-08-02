import type { Metadata } from 'next';

import {
  MenuListing,
  VariantLayout,
} from '@restaurant-engine/storefront-renderer';

import { AddToCartButton } from '../../components/ordering/AddToCartButton';
import { CartLink } from '../../components/ordering/CartLink';
import {
  requirePublicAvailability,
  requirePublicMenu,
  requirePublishedStorefront,
} from '../../lib/server/page-data';
import { storefrontMetadata } from '../../lib/server/page-metadata';

// The complete public menu under the tenant's published chrome (ADR-021).
// The route is gated on the published storefront exactly like `/`: the
// design variant and theme live only on the published version, so a
// business that has never published has no public site — and no menu
// page — under any route. One neutral 404 for every ineligible case.
//
// M6C (ADR-026): the page reads the availability projection for the D12
// ordering gate — the third backend read, mirroring the home route's
// M5D precedent. When ordering is on, orderable items carry the
// add-to-order affordance (`is_orderable` finally renders as the fact
// it always was) and the cart link appears; when it is off, the page is
// byte-identical to the pre-ordering menu — no affordance is fabricated.
export const dynamic = 'force-dynamic';

export function generateMetadata(): Promise<Metadata> {
  return storefrontMetadata('menu');
}

export default async function MenuPage() {
  const storefront = await requirePublishedStorefront();
  const [menu, availability] = await Promise.all([
    requirePublicMenu(),
    requirePublicAvailability(),
  ]);
  const orderingEnabled = availability.pickup.ordering_enabled;
  return (
    <VariantLayout storefront={storefront}>
      <MenuListing
        menu={menu}
        itemAction={
          orderingEnabled
            ? (item) =>
                item.is_orderable ? (
                  <AddToCartButton
                    item={item}
                    currency={menu.business.currency}
                  />
                ) : null
            : undefined
        }
      />
      {orderingEnabled ? <CartLink /> : null}
    </VariantLayout>
  );
}
