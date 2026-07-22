import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { MediaAssetView } from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { unwrapPrivileged } from '../api/failures';
import { menuKeys } from './keys';

/** The media list page size; the contract caps a page at 100. */
export const MEDIA_PAGE_SIZE = 50;

/** One page of the business's media library, newest first. */
export function useMediaPage(
  businessId: string,
  params: { limit: number; offset: number; status?: 'pending' | 'active' },
  enabled = true,
) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: menuKeys.media(businessId, params),
    enabled,
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.media.listAssets(businessId, params),
      ),
  });
}

/**
 * An id → asset map for choosing thumbnail renditions on the overview.
 *
 * One request for the newest active assets, not one per item: a menu may
 * reference dozens of images and per-item lookups would be a request storm.
 * An asset outside this page simply falls back to the canonical rendition,
 * so the map is an optimization that is never load-bearing — nothing renders
 * incorrectly without it.
 */
export function useMediaIndex(businessId: string, enabled: boolean) {
  const page = useMediaPage(
    businessId,
    { limit: 100, offset: 0, status: 'active' },
    enabled,
  );
  const index = new Map<string, MediaAssetView>();
  for (const asset of page.data?.items ?? []) {
    index.set(asset.id, asset);
  }
  return index;
}
