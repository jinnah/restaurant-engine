import type { PublicHeroSection } from '../../lib/contract';
import { assertNever } from '../../lib/assert-never';
import { StorefrontImage } from '../StorefrontImage';
import styles from './sections.module.css';

// The hero call-to-action label is product chrome (neutral English), not
// tenant content. `view_menu` is ordinary in-site navigation (ADR-020 §1);
// the closed HeroAction enum is dispatched exhaustively so the M6 ordering
// member cannot arrive unhandled.
function HeroAction({
  action,
}: {
  action: PublicHeroSection['props']['primary_action'];
}) {
  switch (action) {
    case 'none':
      return null;
    case 'view_menu':
      return (
        <p className={styles.menuLink}>
          <a href="/menu" className={styles.cta}>
            View menu
          </a>
        </p>
      );
    default:
      return assertNever(action);
  }
}

export function HeroSection({ section }: { section: PublicHeroSection }) {
  const { heading, subheading, image, primary_action } = section.props;
  return (
    <section className={`${styles.section} ${styles.hero}`}>
      <h2 className={styles.heroHeading}>{heading}</h2>
      {subheading === null ? null : (
        <p className={styles.heroSubheading}>{subheading}</p>
      )}
      {image === null ? null : (
        <StorefrontImage
          image={image}
          sizes="(max-width: 46rem) 100vw, 46rem"
          loading="eager"
          fetchPriority="high"
          className={styles.heroImage}
        />
      )}
      <HeroAction action={primary_action} />
    </section>
  );
}
