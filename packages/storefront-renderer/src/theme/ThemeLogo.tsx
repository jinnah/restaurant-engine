// The optional tenant logo (M4G-B, ADR-024 §7).
//
// **`alt` is a literal empty string, always, and is never omitted.** The
// logo is permanently decorative: the business name stays the visible
// semantic `h1` in every variant, so an accessible name here would be a
// duplicate announcement of the same fact — the redundancy screen-reader
// users report as noise. `PublicThemeLogo` deliberately carries no
// `alt_text` field precisely so no value can be passed through by
// mistake (M4G-A), which makes emitting `alt=""` this component's own
// obligation. A missing attribute would produce an *unlabelled* image,
// which is a defect, not a decorative image.
//
// Intrinsic `width`/`height` come from the delivered renditions, so the
// box is reserved before the image loads and the header never shifts (no
// CLS). If the media fails to load the chrome stays usable: the name is
// always present as text and the image conveys nothing on its own.
//
// The same component serves the public storefront and the authenticated
// inert preview — there is no preview-specific logo path.

import type { PublicThemeLogo } from '../contract';
import { imageSrcSet } from '../StorefrontImage';

export interface ThemeLogoProps {
  logo: PublicThemeLogo;
  /** Layout hint; each variant sizes its own chrome. */
  sizes?: string;
  className?: string;
}

export function ThemeLogo({
  logo,
  sizes = '12rem',
  className,
}: ThemeLogoProps) {
  return (
    // ADR-021 §6: the platform serves its own authorized responsive
    // renditions, so the raw <img> is deliberate here as it is in
    // StorefrontImage. `imageSrcSet` is reused rather than reimplemented;
    // the logo descriptor is the image descriptor minus `alt_text`, and
    // supplying `null` here only satisfies that shared shape — it never
    // reaches the DOM, because `alt` below is a literal.
    <img
      src={logo.url}
      srcSet={imageSrcSet({ ...logo, alt_text: null })}
      sizes={sizes}
      width={logo.width}
      height={logo.height}
      alt=""
      loading="eager"
      className={className}
    />
  );
}
