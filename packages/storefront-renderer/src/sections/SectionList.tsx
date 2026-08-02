import type { PublicSection } from '../contract';
import { assertNever } from '../assert-never';
import type { LinkMode } from '../links';
import { ContactSection } from './ContactSection';
import { GallerySection } from './GallerySection';
import { HeroSection } from './HeroSection';
import type { HoursSectionData } from './hours-data';
import { HoursSection } from './HoursSection';
import { MenuSection, type MenuSectionData } from './MenuSection';
import { StorySection } from './StorySection';

// The registry-driven dispatch (ADR-021): one renderer per registered
// section type, selected by the discriminant and nothing else. The
// projection's array order is the display order (array order is the
// contract; disabled sections never arrive). The exhaustive switch is the
// renderer's registry teeth — a new section type in the generated
// contract fails the strict typecheck here before it can ship unrendered.
// `menuData` is the public menu composition the menu section renders from
// (null when the page carries no menu section); `hoursData` is the
// availability composition the hours section renders from (M5D, the same
// convention — null when the page carries no availability data). `links`
// is the ADR-022 §3 preview link mode, threaded to the renderers that
// emit in-site navigation.
function renderSection(
  section: PublicSection,
  menuData: MenuSectionData | null,
  hoursData: HoursSectionData | null,
  links: LinkMode,
  orderingEnabled: boolean,
) {
  switch (section.type) {
    case 'hero':
      return (
        <HeroSection
          key={section.id}
          section={section}
          links={links}
          orderingEnabled={orderingEnabled}
        />
      );
    case 'menu':
      return (
        <MenuSection
          key={section.id}
          section={section}
          menuData={menuData}
          links={links}
        />
      );
    case 'story':
      return <StorySection key={section.id} section={section} />;
    case 'contact':
      return <ContactSection key={section.id} section={section} />;
    case 'gallery':
      return <GallerySection key={section.id} section={section} />;
    case 'hours':
      return (
        <HoursSection
          key={section.id}
          section={section}
          hoursData={hoursData}
        />
      );
    default:
      return assertNever(section);
  }
}

export function SectionList({
  sections,
  menuData = null,
  hoursData = null,
  links = 'active',
  orderingEnabled = false,
}: {
  sections: PublicSection[];
  menuData?: MenuSectionData | null;
  hoursData?: HoursSectionData | null;
  links?: LinkMode;
  /**
   * The live D12 gate (M6B): the hero's `order_online` action renders
   * as ordering navigation only when true, degrading to the menu link
   * otherwise. Defaults false, so a consumer without the availability
   * composition (the workspace preview) never fabricates an ordering
   * affordance.
   */
  orderingEnabled?: boolean;
}) {
  return (
    <>
      {sections.map((section) =>
        renderSection(section, menuData, hoursData, links, orderingEnabled),
      )}
    </>
  );
}
