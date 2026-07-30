// Render-facing contract types, derived structurally from the generated
// API client (ADR-004: no handwritten contract copies).
//
// The facade's index exports `DesignVariant`, `PublicSiteSummary`, and the
// `PublicMenu*` family, but not the M4C storefront-projection types — those
// live inside the package's `public` module, which the exports map does not
// expose. Every type below is therefore *derived* from the exported
// `PublicApi` surface rather than retyped: no field is restated, so the
// generated schema remains the single source of truth and a contract change
// propagates here automatically. If the facade later re-exports these types
// directly, this module collapses to plain re-exports.

import type { PublicApi } from '@restaurant-engine/api-client';

/** The success payload of one facade method. */
type OkData<T> =
  Extract<Awaited<T>, { ok: true }> extends { data: infer D } ? D : never;

export type PublicStorefront = OkData<ReturnType<PublicApi['getStorefront']>>;

export type PublicSection = PublicStorefront['sections'][number];
export type PublicHeroSection = Extract<PublicSection, { type: 'hero' }>;
export type PublicMenuSection = Extract<PublicSection, { type: 'menu' }>;
export type PublicStorySection = Extract<PublicSection, { type: 'story' }>;
export type PublicContactSection = Extract<PublicSection, { type: 'contact' }>;
export type PublicGallerySection = Extract<PublicSection, { type: 'gallery' }>;

export type PublicStorefrontImage = NonNullable<
  PublicHeroSection['props']['image']
>;
export type HeroAction = PublicHeroSection['props']['primary_action'];
export type DesignVariant = PublicStorefront['design_variant'];
export type PublicTheme = PublicStorefront['theme'];
