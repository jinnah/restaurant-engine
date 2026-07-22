import type { MediaListParams } from '@restaurant-engine/api-client';

/**
 * Business-workspace query keys.
 *
 * Every key is scoped under `['business', businessId, ...]` so one business's
 * cache can never be read for another, and so `clearAuthenticatedState`'s
 * "remove everything except the session key" predicate sweeps them without a
 * special case (auth/session.ts).
 *
 * `all` is the coarse invalidation key: catalog mutations change positions
 * and counts beyond the row they touched — a delete renormalizes siblings, a
 * category move renormalizes two categories — so invalidating the tree is the
 * honest response to almost every write (ADR-017 D5).
 */
export const menuKeys = {
  all: (businessId: string) => ['business', businessId, 'menu'] as const,
  tree: (businessId: string) =>
    ['business', businessId, 'menu', 'tree'] as const,
  modifiers: (businessId: string, itemId: string) =>
    ['business', businessId, 'menu', 'modifiers', itemId] as const,
  allMedia: (businessId: string) => ['business', businessId, 'media'] as const,
  media: (businessId: string, params: MediaListParams) =>
    ['business', businessId, 'media', 'page', params] as const,
};

export const businessKeys = {
  detail: (businessId: string) => ['business', businessId, 'detail'] as const,
};
