import { notFound } from 'next/navigation';

import { SectionList } from '../components/sections/SectionList';
import { VariantLayout } from '../components/variants/registry';
import { getPublishedStorefront } from '../lib/server/storefront-data';

// The published storefront of the Host-resolved business (ADR-021).
// Request-time SSR only: the published composition changes in place at
// publication and disappears with suspension, so nothing here may be
// static or cached (`no-store` end to end). The backend's neutral 404 —
// unknown host, never published, ineligible lifecycle state — is the one
// neutral not-found page; anything else unrenderable is the generic error
// experience.
export const dynamic = 'force-dynamic';

export default async function HomePage() {
  const result = await getPublishedStorefront();
  if (result.kind === 'not-found') {
    notFound();
  }
  if (result.kind === 'unavailable') {
    throw new Error('storefront backend unavailable');
  }
  const storefront = result.data;
  return (
    <VariantLayout storefront={storefront}>
      <SectionList sections={storefront.sections} />
    </VariantLayout>
  );
}
