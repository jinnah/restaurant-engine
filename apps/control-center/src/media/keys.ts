import type { MediaListParams } from '@restaurant-engine/api-client';

/**
 * Media-library query keys, shared by every consumer of the library (menu
 * item images since M3E; storefront section images since M4E, ADR-022).
 * The key values are unchanged from their original home in `menu/keys.ts`
 * — still `['business', businessId, 'media', ...]` — so cache scoping and
 * the auth sweep behave exactly as before.
 */
export const mediaKeys = {
  all: (businessId: string) => ['business', businessId, 'media'] as const,
  page: (businessId: string, params: MediaListParams) =>
    ['business', businessId, 'media', 'page', params] as const,
};
