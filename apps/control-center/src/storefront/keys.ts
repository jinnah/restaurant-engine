/**
 * Storefront-workspace query keys (ADR-022 §6).
 *
 * Every key is scoped under `['business', businessId, ...]` — the M3E
 * contract — so one business's cache can never be read for another and
 * the auth sweep clears them without a special case.
 *
 * The preview key carries the saved draft's `lock_version` AND
 * `updated_at`: `lock_version` alone collides across publication (the
 * seeded draft's lock restarts), and a colliding key could flash the
 * preceding projection. Mutations additionally remove the whole preview
 * scope (`previewRoot`), so opening preview after save, restore, or
 * publish always loads fresh.
 */
export const storefrontKeys = {
  all: (businessId: string) => ['business', businessId, 'storefront'] as const,
  overview: (businessId: string) =>
    ['business', businessId, 'storefront', 'overview'] as const,
  previewRoot: (businessId: string) =>
    ['business', businessId, 'storefront', 'preview'] as const,
  preview: (businessId: string, lockVersion: number, updatedAt: string) =>
    [
      'business',
      businessId,
      'storefront',
      'preview',
      lockVersion,
      updatedAt,
    ] as const,
  versions: (businessId: string) =>
    ['business', businessId, 'storefront', 'versions'] as const,
  versionsPage: (
    businessId: string,
    params: { limit: number; offset: number },
  ) =>
    ['business', businessId, 'storefront', 'versions', 'page', params] as const,
  version: (businessId: string, versionId: string) =>
    [
      'business',
      businessId,
      'storefront',
      'versions',
      'detail',
      versionId,
    ] as const,
};
