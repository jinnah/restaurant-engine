import { useEffect } from 'react';
import { Link } from 'react-router';

export function NotFoundPage() {
  useEffect(() => {
    document.title = 'Page not found — Restaurant Engine';
  }, []);

  return (
    <section>
      <h1>Page not found</h1>
      <p>This page does not exist.</p>
      <Link to="/">Go to the home page</Link>
    </section>
  );
}
