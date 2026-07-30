'use client';

// Route-segment error boundary — the only client component in the
// storefront (the ADR-021 structural budget allowlists exactly this file).
// Next also passes an `error` prop; it is deliberately not declared,
// because error internals are never rendered: backend bodies, exception
// text, correlation ids, and tenant data stay out of the response.
// Recovery is a reset.
export default function ErrorBoundary({ reset }: { reset: () => void }) {
  return (
    <main>
      <section>
        <h1>Something went wrong</h1>
        <p>An unexpected error occurred.</p>
        <button type="button" onClick={reset}>
          Try again
        </button>
      </section>
    </main>
  );
}
