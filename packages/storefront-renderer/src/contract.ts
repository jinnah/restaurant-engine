// Render-facing contract types (ADR-004: no handwritten contract copies).
//
// The api-client facade now re-exports the M4C projection types — the
// small facade change ADR-021's Consequences approved and ADR-022 §2
// delivered — so this module is exactly the plain re-export collapse that
// ADR-021 predicted. Nothing is restated; the generated schema remains
// the single source of truth.

export type {
  DesignVariant,
  HeroAction,
  PaletteId,
  PublicContactSection,
  PublicGallerySection,
  PublicHeroSection,
  PublicHoursSection,
  PublicMenuSection,
  PublicScheduleException,
  PublicSection,
  PublicStorefront,
  PublicStorefrontImage,
  PublicStorySection,
  PublicTheme,
  PublicThemeLogo,
  PublicWeeklyInterval,
  TypePairingId,
} from '@restaurant-engine/api-client';
