import { createBrowserRouter, type RouteObject } from 'react-router';
import { GuestOnly } from './auth/GuestOnly';
import { RequireAuth } from './auth/RequireAuth';
import { AppLayout } from './routes/AppLayout';
import { ErrorPage } from './routes/ErrorPage';
import { LoginPage } from './routes/LoginPage';
import { MembershipsHome } from './routes/MembershipsHome';
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
        children: [
          {
            element: <AppLayout />,
            children: [{ index: true, element: <MembershipsHome /> }],
          },
        ],
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
