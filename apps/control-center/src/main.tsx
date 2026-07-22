import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { ClientProvider } from './api/ClientProvider';
import { createBrowserClient } from './api/client';
import { createQueryClient } from './api/queryClient';
import { NotificationProvider } from './components/NotificationProvider';
import { router } from './router';
import './globals.css';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('Root container #root is missing from index.html');
}

createRoot(container).render(
  <StrictMode>
    <ClientProvider client={createBrowserClient()}>
      <QueryClientProvider client={createQueryClient()}>
        <NotificationProvider>
          <RouterProvider router={router} />
        </NotificationProvider>
      </QueryClientProvider>
    </ClientProvider>
  </StrictMode>,
);
