import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../api/ClientProvider';
import { unwrapPrivileged } from '../api/failures';
import { businessKeys, menuKeys } from './keys';

/**
 * The business's own record. The session's membership summary carries the
 * name, role, and status but not the currency, and prices cannot be rendered
 * without it (ADR-017 D8: the currency lives on the Business, never on an
 * item), so the workspace reads it once here.
 */
export function useBusiness(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: businessKeys.detail(businessId),
    queryFn: async () =>
      unwrapPrivileged(queryClient, await client.businesses.get(businessId)),
  });
}

/**
 * The complete administrative menu tree: every category and item, hidden
 * ones included. One request — the policy ceilings (50 categories, 300
 * items) keep it bounded, and there is no server-side search or pagination
 * to reach for, so filtering happens over this loaded tree.
 */
export function useAdminMenu(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: menuKeys.tree(businessId),
    queryFn: async () =>
      unwrapPrivileged(queryClient, await client.catalog.getMenu(businessId)),
  });
}
