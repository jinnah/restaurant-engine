import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Page not found — Restaurant Engine',
};

export default function NotFound() {
  return (
    <section>
      <h1>Page not found</h1>
      <p>This page does not exist.</p>
      <Link href="/">Go to the home page</Link>
    </section>
  );
}
