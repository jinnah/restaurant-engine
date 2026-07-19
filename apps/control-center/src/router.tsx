import { createBrowserRouter, type RouteObject } from 'react-router';
import { GuestOnly } from './auth/GuestOnly';
import { RequireAuth } from './auth/RequireAuth';
import { BusinessDetailPage } from './platform/BusinessDetailPage';
import { BusinessesListPage } from './platform/BusinessesListPage';
import { PlatformLayout } from './platform/PlatformLayout';
import { PlatformOverview } from './platform/PlatformOverview';
import { RecoveryPage } from './platform/RecoveryPage';
import { RequirePlatformAdmin } from './platform/RequirePlatformAdmin';
import { AcceptInvitationPage } from './routes/AcceptInvitationPage';
import { AppLayout } from './routes/AppLayout';
import { ErrorPage } from './routes/ErrorPage';
import { LoginPage } from './routes/LoginPage';
import { MembershipsHome } from './routes/MembershipsHome';
import { NotFoundPage } from './routes/NotFoundPage';
import { PasswordResetPage } from './routes/PasswordResetPage';
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
            children: [
              { index: true, element: <MembershipsHome /> },
              {
                path: 'platform',
                element: <RequirePlatformAdmin />,
                children: [
                  {
                    element: <PlatformLayout />,
                    children: [
                      { index: true, element: <PlatformOverview /> },
                      { path: 'businesses', element: <BusinessesListPage /> },
                      {
                        path: 'businesses/:businessId',
                        element: <BusinessDetailPage />,
                      },
                      { path: 'recovery', element: <RecoveryPage /> },
                      // The audit page lands in the following M2F slice;
                      // unknown children 404 below.
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
      {
        element: <GuestOnly />,
        children: [{ path: 'login', element: <LoginPage /> }],
      },
      { path: 'invitations/accept', element: <AcceptInvitationPage /> },
      { path: 'password-reset', element: <PasswordResetPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
