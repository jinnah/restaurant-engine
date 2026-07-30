import { SectionList } from '../components/sections/SectionList';
import { VariantLayout } from '../components/variants/registry';
import {
  menuSectionData,
  requirePublicMenu,
  requirePublishedStorefront,
} from '../lib/server/page-data';

// The published storefront of the Host-resolved business (ADR-021).
// Request-time SSR only: the published composition changes in place at
// publication and disappears with suspension, so nothing here may be
// static or cached (`no-store` end to end). The backend's neutral 404 —
// unknown host, never published, ineligible lifecycle state — is the one
// neutral not-found page; anything else unrenderable is the generic error
// experience. The public menu is fetched only when an enabled menu
// section composes with it.
export const dynamic = 'force-dynamic';

export default async function HomePage() {
  const storefront = await requirePublishedStorefront();
  const hasMenuSection = storefront.sections.some(
    (section) => section.type === 'menu',
  );
  const menuData = hasMenuSection
    ? menuSectionData(await requirePublicMenu())
    : null;
  return (
    <VariantLayout storefront={storefront}>
      <SectionList sections={storefront.sections} menuData={menuData} />
    </VariantLayout>
  );
}
