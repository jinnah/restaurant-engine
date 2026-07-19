import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { BusinessCreate } from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { ApiFailure } from '../api/failure';
import { currentCsrfToken } from '../auth/csrf';
import { unwrapPrivileged } from './api';
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
