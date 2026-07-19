import { createContext, useContext, type ReactNode } from 'react';
import type { ApiClient } from '@restaurant-engine/api-client';

// The facade client reaches components through context so tests inject a
// fake and production injects the browser client — never a module-level
// singleton (ADR-015).
const ClientContext = createContext<ApiClient | null>(null);

export function ClientProvider({
  client,
  children,
}: {
  client: ApiClient;
  children: ReactNode;
}) {
  return (
    <ClientContext.Provider value={client}>{children}</ClientContext.Provider>
  );
}

export function useApiClient(): ApiClient {
  const client = useContext(ClientContext);
  if (client === null) {
    throw new Error('useApiClient requires a <ClientProvider> ancestor.');
  }
  return client;
}
