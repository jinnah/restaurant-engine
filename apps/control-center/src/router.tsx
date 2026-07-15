import { createBrowserRouter, type RouteObject } from 'react-router';
import { ErrorPage } from './routes/ErrorPage';
import { HomePage } from './routes/HomePage';
import { NotFoundPage } from './routes/NotFoundPage';
import { RootLayout } from './routes/RootLayout';

// Exported separately so tests exercise the real route table through a
// memory router.
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
