import type { PublicHeroSection } from '../contract';
import { assertNever } from '../assert-never';
import { siteLinkHref, type LinkMode } from '../links';
import { StorefrontImage } from '../StorefrontImage';
import styles from './sections.module.css';

// The hero call-to-action label is product chrome (neutral English), not
// tenant content. `view_menu` is ordinary in-site navigation (ADR-020 §1);
// `order_online` is the M6 member (ADR-026 D12), gated on the live
// `ordering_enabled` fact at render time: entitlement is platform state
// that changes independently of published content, so a hero authored
// with the ordering action degrades to the plain menu link whenever
// ordering is off — never a dead link, never a frozen entitlement. The
// closed enum is dispatched exhaustively so a future member cannot
// arrive unhandled.
function HeroAction({
  action,
  links,
  orderingEnabled,
}: {
  action: PublicHeroSection['props']['primary_action'];
  links: LinkMode;
  orderingEnabled: boolean;
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
    case 'order_online':
      if (!orderingEnabled) {
        return (
          <p className={styles.menuLink}>
            <a href={siteLinkHref(links, '/menu')} className={styles.cta}>
              View menu
            </a>
          </p>
        );
      }
      return (
        <p className={styles.menuLink}>
          <a href={siteLinkHref(links, '/order')} className={styles.cta}>
            Order online
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
  orderingEnabled = false,
}: {
  section: PublicHeroSection;
  links?: LinkMode;
  orderingEnabled?: boolean;
}) {
  const { heading, subheading, image, primary_action } = section.props;
  return (
    <section
      className={`${styles.section} ${styles.hero}`}
      data-section-type="hero"
    >
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
      <HeroAction
        action={primary_action}
        links={links}
        orderingEnabled={orderingEnabled}
      />
    </section>
  );
}
