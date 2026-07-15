import { useEffect } from 'react';
import { isRouteErrorResponse, Link, useRouteError } from 'react-router';

// Router-level error boundary: renders outside RootLayout, so it carries its
// own landmarks.
export function ErrorPage() {
  const error = useRouteError();

  useEffect(() => {
    document.title = 'Something went wrong — Restaurant Engine';
  }, []);

  return (
    <main>
      <h1>Something went wrong</h1>
      <p>
        {isRouteErrorResponse(error)
          ? `${String(error.status)} ${error.statusText}`
          : 'An unexpected error occurred.'}
      </p>
      <Link to="/">Go to the home page</Link>
    </main>
  );
}
