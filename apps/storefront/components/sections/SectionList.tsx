import type { PublicSection } from '../../lib/contract';
import { assertNever } from '../../lib/assert-never';
import { ContactSection } from './ContactSection';
import { GallerySection } from './GallerySection';
import { HeroSection } from './HeroSection';
import { MenuSection } from './MenuSection';
import { StorySection } from './StorySection';

// The registry-driven dispatch (ADR-021): one renderer per registered
// section type, selected by the discriminant and nothing else. The
// projection's array order is the display order (array order is the
// contract; disabled sections never arrive). The exhaustive switch is the
// renderer's registry teeth — a sixth section type in the generated
// contract fails the strict typecheck here before it can ship unrendered.
function renderSection(section: PublicSection) {
  switch (section.type) {
    case 'hero':
      return <HeroSection key={section.id} section={section} />;
    case 'menu':
      return <MenuSection key={section.id} section={section} />;
    case 'story':
      return <StorySection key={section.id} section={section} />;
    case 'contact':
      return <ContactSection key={section.id} section={section} />;
    case 'gallery':
      return <GallerySection key={section.id} section={section} />;
    default:
      return assertNever(section);
  }
}

export function SectionList({ sections }: { sections: PublicSection[] }) {
  return <>{sections.map(renderSection)}</>;
}
