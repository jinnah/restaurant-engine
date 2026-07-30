import type { Metadata } from 'next';

// Plain anchors throughout the storefront (ADR-021): navigation is full
// page loads — there is no client-side navigation machinery to enhance.

// The one neutral not-found experience (ADR-021). Every public failure the
// backend answers with its neutral 404 — unknown host, no published
// storefront, suspended or otherwise ineligible business — and every
// unknown path renders exactly this page, so the response discloses
// nothing about which case occurred (ADR-013). No tenant data, no cause,
// no platform branding; not indexable.
export const metadata: Metadata = {
  title: 'Page not found',
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <main>
      <section>
        <h1>Page not found</h1>
        <p>This page does not exist.</p>
      </section>
    </main>
  );
}
