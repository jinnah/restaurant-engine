import type { Metadata } from 'next';

import { VariantLayout } from '@restaurant-engine/storefront-renderer';

import { OrderTracker } from '../../../../components/ordering/OrderTracker';
import { requirePublishedStorefront } from '../../../../lib/server/page-data';
import { storefrontMetadata } from '../../../../lib/server/page-metadata';

// The tracking page (M6C, ADR-026). Deliberately NOT gated on the
// ordering entitlement (D10 as amended): an order already placed stays
// trackable after the platform revokes ordering, so this shell requires
// only the published storefront chrome — the same gate as every public
// page. The token authorizes nothing here; the tracker island holds it
// and the backend answers by possession plus Host. Non-indexable by
// policy (a tracking URL is shareable, never discoverable).
export const dynamic = 'force-dynamic';

export function generateMetadata(): Promise<Metadata> {
  return storefrontMetadata('track');
}

export default async function TrackPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const storefront = await requirePublishedStorefront();
  return (
    <VariantLayout storefront={storefront}>
      <OrderTracker token={token} />
    </VariantLayout>
  );
}
