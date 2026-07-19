import { render } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router';
import type { ApiClient } from '@restaurant-engine/api-client';
import { ClientProvider } from '../../src/api/ClientProvider';
import { createQueryClient } from '../../src/api/queryClient';
import { routes } from '../../src/router';

/** Render the real route table with an injected client and query cache. */
export function renderApp(path: string, client: ApiClient) {
  const queryClient = createQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <ClientProvider client={client}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ClientProvider>,
  );
  return { view, router, queryClient };
}
