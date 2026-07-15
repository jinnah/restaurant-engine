import { useEffect } from 'react';

export function HomePage() {
  useEffect(() => {
    document.title = 'Control Center — Restaurant Engine';
  }, []);

  return (
    <section>
      <h1>Restaurant Engine — Control Center</h1>
      <p>
        This is the operational workspace foundation (Milestone 1). Restaurant
        management workflows arrive in later milestones.
      </p>
    </section>
  );
}
