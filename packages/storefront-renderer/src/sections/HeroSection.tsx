import type { PublicHeroSection } from '../contract';
import { assertNever } from '../assert-never';
import { siteLinkHref, type LinkMode } from '../links';
import { StorefrontImage } from '../StorefrontImage';
import styles from './sections.module.css';

// The hero call-to-action label is product chrome (neutral English), not
// tenant content. `view_menu` is ordinary in-site navigation (ADR-020 §1);
// the closed HeroAction enum is dispatched exhaustively so the M6 ordering
// member cannot arrive unhandled.
function HeroAction({
  action,
  links,
}: {
  action: PublicHeroSection['props']['primary_action'];
  links: LinkMode;
}) {
  switch (action) {
    case 'none':
      return null;
    case 'view_menu':
      return (
        <p className={styles.menuLink}>
          <a href={siteLinkHref(links, '/menu')} className={styles.cta}>
            View menu
          </a>
        </p>
      );
    default:
      return assertNever(action);
  }
}

export function HeroSection({
  section,
  links = 'active',
}: {
  section: PublicHeroSection;
  links?: LinkMode;
}) {
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
      <HeroAction action={primary_action} links={links} />
    </section>
  );
}
