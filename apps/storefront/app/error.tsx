'use client';

// Route-segment error boundary — the only client component in the shell.
// Next also passes an `error` prop; it is deliberately not declared, because
// error internals are never rendered. Recovery is a reset.
export default function ErrorBoundary({ reset }: { reset: () => void }) {
  return (
    <section>
      <h1>Something went wrong</h1>
      <p>An unexpected error occurred.</p>
      <button type="button" onClick={reset}>
        Try again
      </button>
    </section>
  );
}
