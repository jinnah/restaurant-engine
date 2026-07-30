import type { ReactNode } from 'react';

import type { PublicStorefront } from '../contract';
import { assertNever } from '../assert-never';
import type { LinkMode } from '../links';
import { ClassicLayout } from './classic/ClassicLayout';

// The variant-to-layout registry (ADR-021): a design variant is a
// *renderer* contract (ADR-020), and this dispatch is the renderer side of
// the backend's code-owned variant registry. The exhaustive switch makes
// registration compile-time complete — the second registered variant
// cannot ship without its layout arm. Section renderers are shared; a
// variant controls page chrome, composition, and scoped styling only.
//
// A 200 projection can only carry a registered variant (the backend fails
// closed on unregistered stored values), so runtime drift here throws into
// the generic error boundary rather than rendering something wrong.

export interface VariantLayoutProps {
  storefront: PublicStorefront;
  children: ReactNode;
  /** Preview link mode (ADR-022 §3); the public storefront omits it. */
  links?: LinkMode;
}

export function VariantLayout({
  storefront,
  children,
  links = 'active',
}: VariantLayoutProps) {
  const variant = storefront.design_variant;
  switch (variant) {
    case 'classic':
      return (
        <ClassicLayout storefront={storefront} links={links}>
          {children}
        </ClassicLayout>
      );
    default:
      return assertNever(variant);
  }
}
