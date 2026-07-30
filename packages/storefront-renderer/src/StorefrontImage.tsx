// One image, rendered from the projection's URL descriptors and nothing
// else (ADR-021). The backend already produces the canonical WebP and its
// strictly narrower responsive renditions (M3C), each with true pixel
// dimensions — so `srcset`/`sizes` come straight from the payload and the
// intrinsic width/height reserve layout space (no CLS). `next/image` is
// deliberately not used: it would insert a second image pipeline (its own
// optimizer, cache, and remote-loader configuration) in front of renditions
// the platform already generates and authorizes per tenant.
//
// Alt text is the placement's contextual alt exactly as delivered; a
// missing alt renders as `alt=""` (decorative) — never an invented
// description.

import type { PublicStorefrontImage } from './contract';

export interface StorefrontImageProps {
  image: PublicStorefrontImage;
  sizes: string;
  loading: 'lazy' | 'eager';
  fetchPriority?: 'high';
  className?: string;
}

export function imageSrcSet(image: PublicStorefrontImage): string {
  const candidates = [
    ...image.variants.map((v) => `${v.url} ${String(v.width)}w`),
    `${image.url} ${String(image.width)}w`,
  ];
  return candidates.join(', ');
}

export function StorefrontImage({
  image,
  sizes,
  loading,
  fetchPriority,
  className,
}: StorefrontImageProps) {
  return (
    // ADR-021: the platform serves its own authorized responsive
    // renditions; Next's optimizer pipeline is deliberately not placed in
    // front of them. This package is framework-neutral, so the raw <img>
    // needs no suppression here; the Next rule still guards the app,
    // which renders images only through this component.
    <img
      src={image.url}
      srcSet={imageSrcSet(image)}
      sizes={sizes}
      width={image.width}
      height={image.height}
      alt={image.alt_text ?? ''}
      loading={loading}
      fetchPriority={fetchPriority}
      className={className}
    />
  );
}
