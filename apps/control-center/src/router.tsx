import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';
import { GuestOnly } from './auth/GuestOnly';
import { RequireAuth } from './auth/RequireAuth';
import { BusinessWorkspaceLayout } from './business/BusinessWorkspaceLayout';
import { RequireBusinessMembership } from './business/RequireBusinessMembership';
import { HoursPage } from './hours/HoursPage';
import { ItemCreatePage } from './menu/ItemCreatePage';
import { OrdersPage } from './orders/OrdersPage';
import { ItemEditorPage } from './menu/ItemEditorPage';
import { MenuOverviewPage } from './menu/MenuOverviewPage';
import { AuditPage } from './platform/AuditPage';
import { StorefrontHistoryPage } from './storefront/StorefrontHistoryPage';
import { StorefrontOverviewPage } from './storefront/StorefrontOverviewPage';
import { StorefrontPreviewPage } from './storefront/StorefrontPreviewPage';
import { StorefrontVersionDetailPage } from './storefront/StorefrontVersionDetailPage';
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
                // The business workspace (ADR-018). `businesses`, never
                // `restaurants`: ADR-012 renamed the tenant aggregate and the
                // blueprint route sketch was amended to match.
                path: 'businesses/:businessId',
                element: <RequireBusinessMembership />,
                children: [
                  {
                    element: <BusinessWorkspaceLayout />,
                    children: [
                      { index: true, element: <Navigate to="menu" replace /> },
                      { path: 'menu', element: <MenuOverviewPage /> },
                      // React Router ranks a static segment above a dynamic
                      // one, so `new` can never be captured as an :itemId.
                      { path: 'menu/items/new', element: <ItemCreatePage /> },
                      {
                        path: 'menu/items/:itemId',
                        element: <ItemEditorPage />,
                      },
                      // The storefront workspace (ADR-022 §1): four
                      // deep-linkable full pages.
                      {
                        path: 'storefront',
                        element: <StorefrontOverviewPage />,
                      },
                      {
                        path: 'storefront/preview',
                        element: <StorefrontPreviewPage />,
                      },
                      {
                        path: 'storefront/history',
                        element: <StorefrontHistoryPage />,
                      },
                      {
                        path: 'storefront/history/:versionId',
                        element: <StorefrontVersionDetailPage />,
                      },
                      // The hours workspace (ADR-025 §M5C): one page for
                      // the weekly schedule, exceptions, and fulfillment.
                      { path: 'hours', element: <HoursPage /> },
                      // The order board (ADR-027 §M7C): every role
                      // operates it (the D2 capability).
                      { path: 'orders', element: <OrdersPage /> },
                      // Unknown workspace children fall through to the root
                      // catch-all not-found route.
                    ],
                  },
                ],
              },
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
                      { path: 'audit', element: <AuditPage /> },
                      // Unknown platform children fall through to the
                      // root catch-all not-found route.
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
