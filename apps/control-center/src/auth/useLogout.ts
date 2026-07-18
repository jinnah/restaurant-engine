import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../api/ClientProvider';
import { ApiFailure } from '../api/failure';
import { currentCsrfToken } from './csrf';
import { clearAuthenticatedState } from './session';

/**
 * Revoke the current session. The CSRF token is read from the session
 * cache at call time (never captured earlier). Success — and the
 * privileged 401 of an already-dead session — immediately clears every
 * trace of authenticated state; other failures surface for retry.
 */
export function useLogout() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const csrfToken = currentCsrfToken(queryClient);
      if (csrfToken === null) {
        await clearAuthenticatedState(queryClient);
        return;
      }
      const result = await client.auth.logout(csrfToken);
      if (result.ok || result.status === 401) {
        await clearAuthenticatedState(queryClient);
        return;
      }
      throw new ApiFailure(result.status, result.envelope);
    },
  });
}
