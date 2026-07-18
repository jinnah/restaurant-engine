import { createBrowserRouter, type RouteObject } from 'react-router';
import { GuestOnly } from './auth/GuestOnly';
import { RequireAuth } from './auth/RequireAuth';
import { ErrorPage } from './routes/ErrorPage';
import { HomePage } from './routes/HomePage';
import { LoginPage } from './routes/LoginPage';
import { NotFoundPage } from './routes/NotFoundPage';
import { RootLayout } from './routes/RootLayout';

// Exported separately so tests exercise the real route table through a
// memory router. Guards are UX only: the API stays the authorization
// authority for every privileged response (docs/02).
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      {
        element: <RequireAuth />,
        children: [{ index: true, element: <HomePage /> }],
      },
      {
        element: <GuestOnly />,
        children: [{ path: 'login', element: <LoginPage /> }],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
