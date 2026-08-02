// Public storefront facade (M2C site; M3D menu; M4C storefront).
//
// The Business is resolved server-side from the request's destination Host
// (same-origin with the tenant subdomain). These methods take NO business,
// slug, Host, or tenant argument and send no tenant-selection header, query
// parameter, body, or cookie of their own — a caller cannot select a tenant.
// The facade does not resolve tenancy. Consumed by the storefront from M4D.
//
// There is deliberately no media URL builder: every image URL a consumer
// needs already arrives inside the menu and storefront payloads, relative
// and same-origin.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type PublicSiteSummary = components['schemas']['PublicSiteSummary'];
export type PublicMenu = components['schemas']['PublicMenu'];
export type PublicMenuCategory = components['schemas']['PublicMenuCategory'];
export type PublicMenuItem = components['schemas']['PublicMenuItem'];
export type PublicMenuImage = components['schemas']['PublicMenuImage'];
export type PublicMenuImageVariant =
  components['schemas']['PublicMenuImageVariant'];
export type PublicModifierGroup = components['schemas']['PublicModifierGroup'];
export type PublicModifierOption =
  components['schemas']['PublicModifierOption'];
export type PublicStorefront = components['schemas']['PublicStorefront'];
export type PublicTheme = components['schemas']['PublicTheme'];
export type PublicThemeLogo = components['schemas']['PublicThemeLogo'];
export type PublicStorefrontImage =
  components['schemas']['PublicStorefrontImage'];
export type PublicStorefrontImageVariant =
  components['schemas']['PublicStorefrontImageVariant'];
export type PublicHeroSection = components['schemas']['PublicHeroSection'];
export type PublicMenuSection = components['schemas']['PublicMenuSection'];
export type PublicStorySection = components['schemas']['PublicStorySection'];
export type PublicContactSection =
  components['schemas']['PublicContactSection'];
export type PublicGallerySection =
  components['schemas']['PublicGallerySection'];
/**
 * One enabled section of the published projection (the members carry the
 * `type` discriminant). Named here because the OpenAPI document publishes
 * the union inline on `PublicStorefront.sections` rather than as a
 * component (ADR-022 §2).
 */
export type PublicSection = PublicStorefront['sections'][number];
export type HeroAction = components['schemas']['HeroAction'];
// M5B (ADR-025): the host-resolved availability projection.
export type PublicAvailability = components['schemas']['PublicAvailability'];
export type PublicWeeklyInterval =
  components['schemas']['PublicWeeklyInterval'];
export type PublicScheduleException =
  components['schemas']['PublicScheduleException'];
export type PublicPickup = components['schemas']['PublicPickup'];

export interface PublicApi {
  getSite(): Promise<ApiResult<PublicSiteSummary>>;
  /** The public menu of the Host-resolved Business (no tenant argument). */
  getMenu(): Promise<ApiResult<PublicMenu>>;
  /**
   * The published storefront projection of the Host-resolved Business
   * (M4C): enabled sections of the currently published version only. 404
   * for a business that has never published — including one holding only
   * a draft.
   */
  getStorefront(): Promise<ApiResult<PublicStorefront>>;
  /**
   * The structured hours of the Host-resolved Business (M5B): weekly
   * schedule, upcoming exceptions, open/closed instant facts, pickup.
   * Every active business answers — no configured hours is honestly
   * closed, not a 404. Never cached (ruling D4): consumers must not
   * store it beyond the render that requested it.
   */
  getAvailability(): Promise<ApiResult<PublicAvailability>>;
}

export function createPublicApi(client: Client<paths>): PublicApi {
  return {
    async getSite() {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/public/site',
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getMenu() {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/public/menu',
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getStorefront() {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/public/storefront',
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getAvailability() {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/public/availability',
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
