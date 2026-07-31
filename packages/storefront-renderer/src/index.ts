// Public surface of @restaurant-engine/storefront-renderer (ADR-022 §2).
//
// The framework-neutral visual rendering of a published storefront
// projection, shared verbatim by the public storefront (server
// components) and the control-center authenticated preview. Everything
// here is a plain React component or pure helper: no 'use client', no
// framework import, no network access, no tenant state. Host resolution,
// data loading, metadata, JSON-LD, and lifecycle/error behavior stay in
// `apps/storefront`.

import baseStyles from './base.module.css';

/**
 * The tenant-page baseline class (base.module.css): the storefront root
 * layout applies it to `<body>`; the control-center preview applies it to
 * the preview container. The fallback only satisfies
 * `noUncheckedIndexedAccess` — the class exists in the committed
 * stylesheet, and the css-policy suite pins it.
 */
export const tenantPageClass: string = baseStyles['tenantPage'] ?? '';

export { VariantLayout, type VariantLayoutProps } from './variants/registry';
export { SectionList } from './sections/SectionList';
export { MenuSection, type MenuSectionData } from './sections/MenuSection';
export { HeroSection } from './sections/HeroSection';
export { StorySection, storyParagraphs } from './sections/StorySection';
export { ContactSection } from './sections/ContactSection';
export { GallerySection } from './sections/GallerySection';
export { MenuListing } from './menu/MenuListing';
export {
  StorefrontImage,
  imageSrcSet,
  type StorefrontImageProps,
} from './StorefrontImage';
export { siteLinkHref, type LinkMode } from './links';
export {
  DEFAULT_ACCENT,
  accentForeground,
  contrastRatio,
  isValidAccent,
  relativeLuminance,
  safeAccent,
} from './accent';
export { themeStyle } from './theme/theme-style';
export {
  PALETTE_IDS,
  paletteTokens,
  type PaletteTokens,
} from './theme/palettes';
export {
  DELIVERED_BODY_STACK,
  TYPE_PAIRING_IDS,
  typePairingTokens,
  type TypePairingTokens,
} from './theme/type-pairings';
export { formatMinorUnits, minorUnitsToDecimalString } from './money';
export { mailtoHref, telHref } from './contact-links';
export { assertNever } from './assert-never';
export type {
  DesignVariant,
  HeroAction,
  PaletteId,
  PublicContactSection,
  PublicGallerySection,
  PublicHeroSection,
  PublicMenuSection,
  PublicSection,
  PublicStorefront,
  PublicStorefrontImage,
  PublicStorySection,
  PublicTheme,
  PublicThemeLogo,
  TypePairingId,
} from './contract';
