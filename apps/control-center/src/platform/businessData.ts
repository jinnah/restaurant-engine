import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  BusinessCreate,
  DesignAssignment,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { ApiFailure } from '../api/failure';
import { currentCsrfToken } from '../auth/csrf';
import { unwrapPrivileged } from '../api/failures';
import { platformKeys, type PageParams } from './keys';

export function usePlatformBusinesses(page: PageParams) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: platformKeys.businesses(page),
    queryFn: async () =>
      unwrapPrivileged(queryClient, await client.platform.listBusinesses(page)),
  });
}

export function usePlatformBusiness(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: platformKeys.business(businessId),
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.platform.getBusiness(businessId),
      ),
  });
}

export type LifecycleAction = 'activate' | 'suspend' | 'reactivate' | 'close';

/**
 * Run a lifecycle command. The command response is the authoritative
 * updated representation, so it is written straight into the detail
 * cache; every businesses list page is invalidated for refetch.
 */
export function useLifecycleAction(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (action: LifecycleAction) => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(401, null);
      }
      return unwrapPrivileged(
        queryClient,
        await client.platform[action](businessId, csrfToken),
      );
    },
    onSuccess: async (updated) => {
      queryClient.setQueryData(platformKeys.business(businessId), updated);
      await queryClient.invalidateQueries({
        queryKey: platformKeys.allBusinesses(),
      });
    },
  });
}

/**
 * Assign the storefront draft's structural design variant (M4B command,
 * first UI in M4G-C; ADR-020 §6).
 *
 * No cache is written or invalidated on success, and that is deliberate:
 * the platform business representation carries no design variant, so there
 * is nothing cached here that the command makes stale. The acknowledgment
 * itself is the only fact the page may report, and the caller renders it
 * verbatim rather than inferring a new client-side "current" value.
 *
 * The command takes no `expected_lock_version` — it is serialized by the
 * Business row lock, not by the owner-facing draft token.
 */
export function useSetDesign(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: DesignAssignment) => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(401, null);
      }
      return unwrapPrivileged(
        queryClient,
        await client.platform.setDesign(businessId, body, csrfToken),
      );
    },
  });
}

/** Create a business; success refreshes every businesses list page. */
export function useCreateBusiness() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: BusinessCreate) => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(401, null);
      }
      return unwrapPrivileged(
        queryClient,
        await client.platform.createBusiness(body, csrfToken),
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: platformKeys.allBusinesses(),
      });
    },
  });
}
