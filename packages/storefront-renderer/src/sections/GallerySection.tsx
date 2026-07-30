import type { PublicGallerySection } from '../contract';
import { StorefrontImage } from '../StorefrontImage';
import styles from './sections.module.css';

// The projection already resolved every reference to a renderable asset
// (missing assets degrade by omission, ADR-020 §10). A gallery left with
// nothing renderable renders nothing at all — an empty frame would be
// fabricated structure. Gallery media sits below the fold and lazy-loads.
export function GallerySection({ section }: { section: PublicGallerySection }) {
  const { heading, images } = section.props;
  if (images.length === 0) {
    return null;
  }
  return (
    <section className={styles.section}>
      {heading === null ? null : <h2 className={styles.heading}>{heading}</h2>}
      <ul className={styles.galleryGrid}>
        {images.map((image) => (
          <li key={image.url} className={styles.galleryItem}>
            <StorefrontImage
              image={image}
              sizes="(max-width: 46rem) 50vw, 15rem"
              loading="lazy"
              className={styles.galleryImage}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
