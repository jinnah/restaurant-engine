import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  ModifierGroupCreate,
  ModifierGroupUpdate,
  ModifierOptionCreate,
  ModifierOptionUpdate,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { requireCsrf, unwrapPrivileged } from '../api/failures';
import { menuKeys } from './keys';

/**
 * One item's modifier tree.
 *
 * Groups belong to exactly one item and options to exactly one group
 * (ADR-017 D2) — there is no shared modifier library in M3, so this is
 * genuinely per-item data with its own bounded query.
 */
export function useModifierGroups(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: menuKeys.modifiers(businessId, itemId),
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.getModifierGroups(businessId, itemId),
      ),
  });
}

/**
 * Every option mutation returns the recomputed parent group, including its
 * freshly derived `active_option_count` and `is_satisfiable`. Writing that
 * response into the cached tree keeps the satisfiability advisory correct
 * without a refetch — the server has already done the computing.
 */
function useGroupWriter(businessId: string, itemId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({
      queryKey: menuKeys.modifiers(businessId, itemId),
    });
  };
}

export function useCreateGroup(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const refresh = useGroupWriter(businessId, itemId);
  return useMutation({
    mutationFn: async (body: ModifierGroupCreate) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.createModifierGroup(
          businessId,
          itemId,
          body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: refresh,
  });
}

export function useUpdateGroup(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const refresh = useGroupWriter(businessId, itemId);
  return useMutation({
    mutationFn: async (input: { groupId: string; body: ModifierGroupUpdate }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.updateModifierGroup(
          businessId,
          input.groupId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: refresh,
  });
}

export function useDeleteGroup(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const refresh = useGroupWriter(businessId, itemId);
  return useMutation({
    mutationFn: async (groupId: string) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.deleteModifierGroup(
          businessId,
          groupId,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: refresh,
  });
}

export function useReorderGroups(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (orderedIds: string[]) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.reorderModifierGroups(
          businessId,
          itemId,
          { ordered_group_ids: orderedIds },
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (view) => {
      queryClient.setQueryData(menuKeys.modifiers(businessId, itemId), view);
    },
  });
}

export function useCreateOption(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const refresh = useGroupWriter(businessId, itemId);
  return useMutation({
    mutationFn: async (input: {
      groupId: string;
      body: ModifierOptionCreate;
    }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.createModifierOption(
          businessId,
          input.groupId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: refresh,
  });
}

export function useUpdateOption(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const refresh = useGroupWriter(businessId, itemId);
  return useMutation({
    // Availability rides this PATCH (ruling D3): options have no separate
    // availability command, unlike items.
    mutationFn: async (input: {
      optionId: string;
      body: ModifierOptionUpdate;
    }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.updateModifierOption(
          businessId,
          input.optionId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: refresh,
  });
}

export function useDeleteOption(businessId: string, itemId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const refresh = useGroupWriter(businessId, itemId);
  return useMutation({
    mutationFn: async (optionId: string) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.deleteModifierOption(
          businessId,
          optionId,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: refresh,
  });
}
