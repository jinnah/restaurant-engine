import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  InvitationCreate,
  InvitationIssueResponse,
} from '@restaurant-engine/api-client';
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
 * Issue an invitation. The response carries the raw one-time token, so
 * it is handed to `onIssued` (the caller's transient reveal state)
 * inside the mutation function and the mutation itself resolves
 * token-free: neither the query cache nor the TanStack mutation cache
 * ever holds the token. The pending list is refreshed on success.
 */
export function useCreateInvitation(
  businessId: string,
  onIssued: (response: InvitationIssueResponse) => void,
) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: InvitationCreate): Promise<null> => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        throw new ApiFailure(401, null);
      }
      const response = await unwrapPrivileged(
        queryClient,
        await client.platform.createInvitation(businessId, body, csrfToken),
      );
      onIssued(response);
      return null;
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
