import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import {
  tenantPageClass,
  themeStyle,
} from '@restaurant-engine/storefront-renderer';
import { getPublishedStorefront } from '../lib/server/storefront-data';
import './globals.css';

// The root layout is deliberately bare chrome-free structure: every tenant
// page composes its own presentation through the design-variant layout
// (ADR-021), and platform branding never appears on a tenant's storefront.
// The title below is only the neutral fallback for responses that carry no
// page metadata of their own (the generic error experience).
//
// `lang="en"` is the product chrome's language. Tenant copy may be in any
// language (Unicode-capable presentation); a per-tenant document language
// is not modeled yet, and that limitation is recorded in ADR-021.
//
// M4G-B (ADR-024 §5): `<body>` carries the tenant-page baseline class, so
// it is also where the theme's custom properties belong — the browser
// paints the canvas from <body>'s background, and tokens set on a
// descendant would leave the canvas on the baseline palette behind a dark
// page. The loader here is the **non-throwing** cached result: it never
// calls `notFound()`, so the neutral 404 and the generic error document
// keep rendering, unthemed, exactly as before. It is the same
// argument-less `React.cache` loader that `generateMetadata` and the page
// body already call, so the request is deduplicated within the render and
// the measured cost stays at two backend reads per page (ADR-021 §3).
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Storefront',
};

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  const storefront = await getPublishedStorefront();
  return (
    <html lang="en">
      {/* The whole public page is the tenant page, so the shared
          renderer's scoped baseline (ADR-022 §2) applies at <body>. */}
      <body
        className={tenantPageClass}
        style={
          storefront.kind === 'ok'
            ? themeStyle(storefront.data.theme)
            : undefined
        }
      >
        {children}
      </body>
    </html>
  );
}
