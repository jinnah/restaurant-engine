import { QueryClient } from '@tanstack/react-query';

// One deterministic configuration for app and tests: no automatic
// retries (the session queryFn already converts the expected 401 into a
// value, so a retry would only mask real failures) and no focus
// refetching (session revalidation is explicit — login, logout, or a
// user-triggered retry).
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}
