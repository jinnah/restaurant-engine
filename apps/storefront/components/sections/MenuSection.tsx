import type { PublicMenuSection } from '../../lib/contract';
import styles from './sections.module.css';

// The menu section carries heading and intro only — which items appear,
// their order, and featured status are catalog's answer through the public
// menu projection (ADR-020 §2), rendered on `/menu`. The link label is
// product chrome.
export function MenuSection({ section }: { section: PublicMenuSection }) {
  const { heading, intro } = section.props;
  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>{heading}</h2>
      {intro === null ? null : <p className={styles.intro}>{intro}</p>}
      <p className={styles.menuLink}>
        <a href="/menu" className={styles.cta}>
          View the full menu
        </a>
      </p>
    </section>
  );
}
