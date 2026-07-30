import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import type {
  DraftPut,
  DraftView,
  PublishRequest,
  RestoreRequest,
  StorefrontOverview,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { requireCsrf, unwrapPrivileged } from '../api/failures';
import { storefrontKeys } from './keys';

/** One bounded history page (the version list is `version_number DESC`). */
export const HISTORY_PAGE_SIZE = 20;

/**
 * The administrative storefront state: the current draft (or null — the
 * valid first-use absence, ADR-020 §5.1) plus the published summary.
 */
export function useStorefrontOverview(businessId: string, enabled = true) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: storefrontKeys.overview(businessId),
    enabled,
    queryFn: async () =>
      unwrapPrivileged(queryClient, await client.storefront.get(businessId)),
  });
}

/**
 * The render-equivalent projection of the current SAVED draft (M4C
 * preview). Keyed by the draft's `lock_version` and `updated_at`
 * (ADR-022 §6), so a projection can never be served for a draft other
 * than the one it was computed from — and never flash across a save,
 * restore, or publish. The endpoint is `no-store`; the query mirrors
 * that with `staleTime: 0`.
 */
export function useDraftPreview(
  businessId: string,
  draft: { lock_version: number; updated_at: string } | null,
) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey:
      draft === null
        ? storefrontKeys.previewRoot(businessId)
        : storefrontKeys.preview(
            businessId,
            draft.lock_version,
            draft.updated_at,
          ),
    enabled: draft !== null,
    staleTime: 0,
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.storefront.preview(businessId),
      ),
  });
}

/** One history page: the published row plus archived rows, newest first. */
export function useVersionsPage(businessId: string, offset: number) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: storefrontKeys.versionsPage(businessId, {
      limit: HISTORY_PAGE_SIZE,
      offset,
    }),
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.storefront.listVersions(businessId, {
          limit: HISTORY_PAGE_SIZE,
          offset,
        }),
      ),
  });
}

/** One published or archived version with its full composition. */
export function useVersionDetail(
  businessId: string,
  versionId: string,
  enabled = true,
) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: storefrontKeys.version(businessId, versionId),
    enabled,
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.storefront.getVersion(businessId, versionId),
      ),
  });
}

/**
 * Merge a mutation's returned `DraftView` into the cached overview,
 * preserving `published` untouched (ADR-022 §6). A `DraftView` is not a
 * `StorefrontOverview` and must never be written into that key whole;
 * when the overview is not cached at all, invalidate instead of
 * fabricating one.
 */
function mergeDraftIntoOverview(
  queryClient: QueryClient,
  businessId: string,
  draft: DraftView,
): void {
  const key = storefrontKeys.overview(businessId);
  const existing = queryClient.getQueryData<StorefrontOverview>(key);
  if (existing === undefined) {
    void queryClient.invalidateQueries({ queryKey: key });
    return;
  }
  queryClient.setQueryData<StorefrontOverview>(key, {
    ...existing,
    draft,
  });
}

/**
 * Drop every cached preview projection. Removal, not invalidation: an
 * invalidated entry still renders while refetching, which is exactly the
 * stale flash ADR-022 §6 forbids after save, restore, or publish.
 */
function removePreviews(queryClient: QueryClient, businessId: string): void {
  queryClient.removeQueries({
    queryKey: storefrontKeys.previewRoot(businessId),
  });
}

/**
 * Mark the overview stale WITHOUT an active refetch — the §6 conflict
 * rule: after a 409 the form keeps the user's values and stale token, so
 * nothing may rebind it in the background; only the explicit "Reload
 * current draft" action fetches. `refetchType: 'none'` is precisely
 * invalidation-without-refetch.
 */
export function markOverviewStale(
  queryClient: QueryClient,
  businessId: string,
): void {
  void queryClient.invalidateQueries({
    queryKey: storefrontKeys.overview(businessId),
    refetchType: 'none',
  });
}

/**
 * Create or replace the draft — the one full-document PUT (D-5). Intent
 * is the caller's: `expected_lock_version` omitted/null claims "no draft
 * exists" (create); an integer claims that exact version (update). No
 * optimistic update; a stale 409 propagates to the caller's explicit
 * conflict handling and is never retried or merged here.
 */
export function useSaveDraft(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: DraftPut) =>
      unwrapPrivileged(
        queryClient,
        await client.storefront.putDraft(
          businessId,
          body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (draft) => {
      mergeDraftIntoOverview(queryClient, businessId, draft);
      removePreviews(queryClient, businessId);
    },
  });
}

/**
 * Publish the saved draft (owner only; requires its exact lock version,
 * D-3). The response is the authoritative post-publication overview —
 * written wholesale — and the whole versions scope is invalidated: the
 * previously published row's state just flipped to archived, so pages
 * AND details are stale (ADR-022 §6).
 */
export function usePublish(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: PublishRequest) =>
      unwrapPrivileged(
        queryClient,
        await client.storefront.publish(
          businessId,
          body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (overview) => {
      queryClient.setQueryData(storefrontKeys.overview(businessId), overview);
      void queryClient.invalidateQueries({
        queryKey: storefrontKeys.versions(businessId),
      });
      removePreviews(queryClient, businessId);
    },
  });
}

/**
 * Restore an archived version into the draft (owner only; carries the
 * current draft's exact lock version; never publishes). History rows are
 * untouched by a restore, so only the draft merges and the previews
 * drop.
 */
export function useRestoreVersion(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { versionId: string; body: RestoreRequest }) =>
      unwrapPrivileged(
        queryClient,
        await client.storefront.restoreVersion(
          businessId,
          input.versionId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (draft) => {
      mergeDraftIntoOverview(queryClient, businessId, draft);
      removePreviews(queryClient, businessId);
    },
  });
}
