import type { Metadata } from 'next';

import { notFound } from 'next/navigation';

import { VariantLayout } from '@restaurant-engine/storefront-renderer';

import { CheckoutForm } from '../../components/ordering/CheckoutForm';
import { OrderingPausedNotice } from '../../components/ordering/OrderingPausedNotice';
import {
  requirePublicAvailability,
  requirePublishedStorefront,
} from '../../lib/server/page-data';
import { storefrontMetadata } from '../../lib/server/page-metadata';

// The checkout surface (M6C, ADR-026). The route exists only while the
// D12 gate is on: a storefront without ordering shows no ordering
// surface, and this page answers the same neutral 404 as an unknown
// host (D10 — the API behind it refuses identically, so the page and
// the API disclose exactly the same nothing). The gate is read per
// request, never frozen into published content. Non-indexable by
// policy (see page-metadata): the surface is transactional and its
// existence is a live entitlement fact.
//
// M7B (ADR-027 D8): a temporary pause is a DIFFERENT state from the
// gate — the surface exists and is honestly, temporarily off. The
// server renders the customer-visible explanation instead of the
// checkout form; the cart survives untouched in the visitor's browser,
// so resuming finds their order exactly where they left it.
export const dynamic = 'force-dynamic';

export function generateMetadata(): Promise<Metadata> {
  return storefrontMetadata('order');
}

export default async function OrderPage() {
  const storefront = await requirePublishedStorefront();
  const availability = await requirePublicAvailability();
  if (!availability.pickup.ordering_enabled) {
    notFound();
  }
  if (availability.pickup.ordering_paused) {
    return (
      <VariantLayout storefront={storefront}>
        <OrderingPausedNotice
          note={availability.pickup.pause_note}
          resumesAt={availability.pickup.pause_resumes_at}
          timezone={availability.business.timezone}
        />
      </VariantLayout>
    );
  }
  return (
    <VariantLayout storefront={storefront}>
      <CheckoutForm
        currency={availability.business.currency}
        timezone={availability.business.timezone}
        asapEnabled={availability.pickup.asap_enabled}
      />
    </VariantLayout>
  );
}
