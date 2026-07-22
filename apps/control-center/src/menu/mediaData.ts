import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { MediaAssetView } from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { requireCsrf, unwrapPrivileged } from '../api/failures';
import { menuKeys } from './keys';

/**
 * The formats the backend accepts (static JPEG, PNG, WebP — ADR-017 M3C).
 *
 * Used as the file picker's `accept` hint and to refuse a clearly wrong
 * type early. It is a courtesy, not a check: the server's magic-byte and
 * decoded-format agreement test is the authority, and an empty or
 * unrecognized `File.type` is passed through for it to judge.
 */
export const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * The smallest upload cap any deployment can be configured with (10 MiB;
 * the setting is bounded 10–20 MiB and is not exposed by the API).
 *
 * Used only to warn. Blocking on it would reject files a 20 MiB deployment
 * would happily accept, so the 413 stays the authority.
 */
export const ADVISORY_MAX_BYTES = 10 * 1024 * 1024;

/** True only for a file whose stated type is definitely unsupported. */
export function isUnsupportedType(type: string): boolean {
  return type !== '' && !ACCEPTED_IMAGE_TYPES.includes(type);
}

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

/**
 * Upload one image.
 *
 * There is no cancellation: the generated client builds its request without
 * an abort signal, so nothing here may claim that leaving cancels an upload
 * (ADR-018 ruling 10). The UI says so plainly instead.
 */
export function useUploadAsset(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) =>
      unwrapPrivileged(
        queryClient,
        await client.media.uploadAsset(
          businessId,
          file,
          file.name,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: menuKeys.allMedia(businessId),
      });
    },
  });
}

/**
 * Delete an asset from the library permanently.
 *
 * Distinct from removing it from an item: a referenced asset cannot be
 * deleted at all (the RESTRICT foreign key surfaces as a 409), and detaching
 * never deletes bytes.
 */
export function useDeleteAsset(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assetId: string) =>
      unwrapPrivileged(
        queryClient,
        await client.media.deleteAsset(
          businessId,
          assetId,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: menuKeys.allMedia(businessId),
      });
    },
  });
}
