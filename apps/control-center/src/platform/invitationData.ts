import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { InvitationCreate } from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { ApiFailure } from '../api/failure';
import { currentCsrfToken } from '../auth/csrf';
import { unwrapPrivileged } from './api';
import { platformKeys, type PageParams } from './keys';

export function usePlatformInvitations(businessId: string, page: PageParams) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: platformKeys.invitations(businessId, page),
    queryFn: async () =>
      unwrapPrivileged(
        queryClient,
        await client.platform.listInvitations(businessId, page),
      ),
  });
}

/**
 * Issue an invitation. The response carries the raw one-time token; it
 * lives only in the caller's transient state (OneTimeTokenReveal) and
 * is never written to any cache. The pending list is refreshed.
 */
export function useCreateInvitation(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: InvitationCreate) => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(401, null);
      }
      return unwrapPrivileged(
        queryClient,
        await client.platform.createInvitation(businessId, body, csrfToken),
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: platformKeys.allInvitations(businessId),
      });
    },
  });
}

export function useRevokeInvitation(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (invitationId: string) => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(401, null);
      }
      return unwrapPrivileged(
        queryClient,
        await client.platform.revokeInvitation(
          businessId,
          invitationId,
          csrfToken,
        ),
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: platformKeys.allInvitations(businessId),
      });
    },
  });
}
