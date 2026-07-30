// Published-data-only document metadata (ADR-021).
//
// Titles, descriptions, canonical URLs, and Open Graph facts derive from
// the published projection and the validated request Host — nothing is
// fabricated, and a request whose backend read is not `ok` gets empty
// metadata (its page renders the neutral 404 or generic error, which
// carry their own non-indexable identity). The canonical origin follows
// the deterministic scheme policy in lib/canonical; the hero image is the
// Open Graph image when one exists, resolved absolute via `metadataBase`.

import type { Metadata } from 'next';

import { canonicalOrigin } from '../canonical';
import { getPublishedStorefront, getRequestHost } from './storefront-data';

const PAGES = {
  home: { canonicalPath: '/', titlePrefix: null },
  menu: { canonicalPath: '/menu', titlePrefix: 'Menu' },
} as const;

export async function storefrontMetadata(
  page: keyof typeof PAGES,
): Promise<Metadata> {
  const result = await getPublishedStorefront();
  if (result.kind !== 'ok') {
    return {};
  }
  const storefront = result.data;
  const host = await getRequestHost();
  const origin = host === null ? null : canonicalOrigin(host);
  const { canonicalPath, titlePrefix } = PAGES[page];
  const name = storefront.business.name;
  const title = titlePrefix === null ? name : `${titlePrefix} — ${name}`;
  const hero =
    page === 'home'
      ? storefront.sections.find((section) => section.type === 'hero')
      : undefined;
  const description = hero?.props.subheading ?? undefined;
  const heroImage = hero?.props.image ?? undefined;
  return {
    title,
    ...(description === undefined ? {} : { description }),
    ...(origin === null
      ? {}
      : {
          metadataBase: new URL(origin),
          alternates: { canonical: canonicalPath },
        }),
    openGraph: {
      title,
      siteName: name,
      type: 'website',
      ...(description === undefined ? {} : { description }),
      ...(heroImage === undefined
        ? {}
        : {
            images: [
              {
                url: heroImage.url,
                width: heroImage.width,
                height: heroImage.height,
                ...(heroImage.alt_text === null
                  ? {}
                  : { alt: heroImage.alt_text }),
              },
            ],
          }),
    },
  };
}
