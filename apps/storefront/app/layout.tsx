import type { Metadata } from 'next';
import type { ReactNode } from 'react';
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
export const metadata: Metadata = {
  title: 'Storefront',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
