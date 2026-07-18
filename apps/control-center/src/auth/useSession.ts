import { useQuery } from '@tanstack/react-query';
import type { SessionView } from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { sessionQueryOptions } from './session';

export type UseSessionResult =
  | { status: 'loading' }
  | { status: 'authenticated'; session: SessionView; csrfToken: string }
  | { status: 'anonymous' }
  | { status: 'error'; retry: () => void };

/**
 * Thin read model over the session query — the only way components
 * observe auth state. `error` means the bootstrap itself failed
 * unexpectedly (never the expected anonymous 401) and is retryable
 * without resubmitting anything sensitive.
 */
export function useSession(): UseSessionResult {
  const client = useApiClient();
  const query = useQuery(sessionQueryOptions(client));

  if (query.isPending) {
    return { status: 'loading' };
  }
  if (query.isError || query.data === undefined) {
    return {
      status: 'error',
      retry: () => {
        void query.refetch();
      },
    };
  }
  return query.data.kind === 'authenticated'
    ? {
        status: 'authenticated',
        session: query.data.session,
        csrfToken: query.data.csrfToken,
      }
    : { status: 'anonymous' };
}
