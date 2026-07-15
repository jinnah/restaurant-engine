import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Storefront — Restaurant Engine',
};

export default function HomePage() {
  return (
    <section>
      <h1>Restaurant Engine — Storefront</h1>
      <p>
        This is the public storefront foundation (Milestone 1). Restaurant
        experiences arrive in later milestones.
      </p>
    </section>
  );
}
