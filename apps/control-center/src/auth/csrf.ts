import type { QueryClient } from '@tanstack/react-query';
import { SESSION_KEY, type SessionState } from './session';

/**
 * The current CSRF token, read from the authoritative session cache at
 * call time (ADR-015): unsafe mutations never capture a token at
 * construction, so a rotated session always supplies the fresh value.
 * There is no second CSRF store.
 */
export function currentCsrfToken(queryClient: QueryClient): string | null {
  const state = queryClient.getQueryData<SessionState>(SESSION_KEY);
  return state !== undefined && state.kind === 'authenticated'
    ? state.csrfToken
    : null;
}
