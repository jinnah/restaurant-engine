import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  CategoryCreate,
  CategoryUpdate,
  ItemCreate,
  ItemImageSet,
  ItemUpdate,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { requireCsrf, unwrapPrivileged } from '../api/failures';
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

/**
 * Invalidate the whole workspace tree after a mutation.
 *
 * Deliberately coarse. A catalog write changes more than the row it touched:
 * deleting an item renormalizes its siblings' positions, moving one
 * renormalizes two categories, and featuring one changes a count the page
 * displays. Refetching the tree is the honest response, and ADR-017 D5
 * requires it — row locks serialize writes but do not detect stale editors,
 * so the client must never assume its cached copy survived someone else's
 * edit.
 */
function useInvalidateMenu(businessId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: menuKeys.all(businessId) });
  };
}

// --- Categories --------------------------------------------------------

export function useCreateCategory(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMenu(businessId);
  return useMutation({
    mutationFn: async (body: CategoryCreate) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.createCategory(
          businessId,
          body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useUpdateCategory(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMenu(businessId);
  return useMutation({
    mutationFn: async (input: { categoryId: string; body: CategoryUpdate }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.updateCategory(
          businessId,
          input.categoryId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useDeleteCategory(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMenu(businessId);
  return useMutation({
    mutationFn: async (categoryId: string) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.deleteCategory(
          businessId,
          categoryId,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: invalidate,
  });
}

/**
 * Reorder categories, or the items inside one category.
 *
 * Both send the complete permutation and both return the authoritative
 * `AdminMenu`, so the response is written straight into the cache rather than
 * triggering another round trip. An inexact set — someone added or removed an
 * entry while the user was reordering — comes back as a 409 and the caller
 * refetches instead of retrying blindly.
 */
export function useReorderCategories(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (orderedIds: string[]) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.reorderCategories(
          businessId,
          { ordered_category_ids: orderedIds },
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (menu) => {
      queryClient.setQueryData(menuKeys.tree(businessId), menu);
    },
  });
}

export function useReorderItems(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { categoryId: string; orderedIds: string[] }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.reorderItems(
          businessId,
          {
            category_id: input.categoryId,
            ordered_item_ids: input.orderedIds,
          },
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (menu) => {
      queryClient.setQueryData(menuKeys.tree(businessId), menu);
    },
  });
}

// --- Items -------------------------------------------------------------

export function useCreateItem(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMenu(businessId);
  return useMutation({
    // The category is a path parameter, not a body field: an item is created
    // *in* a category (ADR-017 D2), and ItemCreate carries no category_id.
    mutationFn: async (input: { categoryId: string; body: ItemCreate }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.createItem(
          businessId,
          input.categoryId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useUpdateItem(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMenu(businessId);
  return useMutation({
    mutationFn: async (input: { itemId: string; body: ItemUpdate }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.updateItem(
          businessId,
          input.itemId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useDeleteItem(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMenu(businessId);
  return useMutation({
    mutationFn: async (itemId: string) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.deleteItem(
          businessId,
          itemId,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: invalidate,
  });
}

/**
 * The "sold out today" toggle — a separate workflow command with its own
 * capability (`business.catalog.availability`), which is why staff can reach
 * it while everything else on this page is closed to them. It is deliberately
 * absent from the item PATCH contract (ruling D4).
 */
export function useSetItemAvailability(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateMenu(businessId);
  return useMutation({
    mutationFn: async (input: { itemId: string; isAvailable: boolean }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.setItemAvailability(
          businessId,
          input.itemId,
          { is_available: input.isAvailable },
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: invalidate,
  });
}

/** Attach, replace, clear, or re-describe an item's image (one command). */
export function useSetItemImage(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { itemId: string; body: ItemImageSet }) =>
      unwrapPrivileged(
        queryClient,
        await client.catalog.setItemImage(
          businessId,
          input.itemId,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: async () => {
      // Attaching promotes the asset pending -> active, so the library's
      // view of it is stale too.
      await queryClient.invalidateQueries({
        queryKey: menuKeys.all(businessId),
      });
      await queryClient.invalidateQueries({
        queryKey: menuKeys.allMedia(businessId),
      });
    },
  });
}
