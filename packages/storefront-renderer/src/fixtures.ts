// Typed payload builders for renderer tests, shaped exactly like the
// generated contract (contract derivations), plus the required
// complex-script fixtures.
//
// The Bengali strings below are ENGINEERING TEST DATA ONLY (ADR-021):
// they exercise conjunct clusters, matras, ZWNJ/ZWJ join control, and NFC
// stability in a real complex script. They are never seed data, defaults,
// or product content, and carry no market meaning.

import type { PublicMenu, PublicMenuItem } from '@restaurant-engine/api-client';

import type {
  PublicContactSection,
  PublicGallerySection,
  PublicHeroSection,
  PublicMenuSection,
  PublicSection,
  PublicStorefront,
  PublicStorefrontImage,
  PublicStorySection,
  PublicTheme,
  PublicThemeLogo,
} from './contract';

/**
 * The delivered presentation: the platform default accent plus the registry
 * defaults every configuration stored before M4G projects (ADR-024 §5), so
 * a fixture that overrides one token keeps the rest realistic.
 */
export function themeFixture(
  overrides: Partial<PublicTheme> = {},
): PublicTheme {
  return {
    accent: '#a34b2a',
    palette: 'warm',
    type_pairing: 'humanist',
    logo: null,
    ...overrides,
  };
}

export function themeLogoFixture(
  overrides: Partial<PublicThemeLogo> = {},
): PublicThemeLogo {
  return {
    width: 480,
    height: 160,
    url: '/api/v1/public/media/00000000-0000-0000-0000-0000000010g0/w640',
    variants: [
      {
        variant: 'w320',
        width: 320,
        height: 107,
        url: '/api/v1/public/media/00000000-0000-0000-0000-0000000010g0/w320',
      },
    ],
    ...overrides,
  };
}

export function imageFixture(
  overrides: Partial<PublicStorefrontImage> = {},
): PublicStorefrontImage {
  return {
    alt_text: 'A plated dish on a wooden table',
    width: 1600,
    height: 1200,
    url: '/api/v1/public/media/00000000-0000-0000-0000-00000000aaaa/w1280',
    variants: [
      {
        variant: 'w320',
        width: 320,
        height: 240,
        url: '/api/v1/public/media/00000000-0000-0000-0000-00000000aaaa/w320',
      },
      {
        variant: 'w640',
        width: 640,
        height: 480,
        url: '/api/v1/public/media/00000000-0000-0000-0000-00000000aaaa/w640',
      },
    ],
    ...overrides,
  };
}

export function heroSection(
  props: Partial<PublicHeroSection['props']> = {},
): PublicHeroSection {
  return {
    id: 'hero-main',
    type: 'hero',
    props: {
      heading: 'Neighborhood kitchen, open late',
      subheading: 'Family recipes, cooked to order',
      image: imageFixture(),
      primary_action: 'view_menu',
      ...props,
    },
  };
}

export function menuSection(
  props: Partial<PublicMenuSection['props']> = {},
): PublicMenuSection {
  return {
    id: 'menu-main',
    type: 'menu',
    props: {
      heading: 'Our menu',
      intro: 'Everything is made fresh daily.',
      ...props,
    },
  };
}

export function storySection(
  props: Partial<PublicStorySection['props']> = {},
): PublicStorySection {
  return {
    id: 'story-main',
    type: 'story',
    props: {
      heading: 'Our story',
      body: 'First paragraph.\nSecond line.\n\nSecond paragraph.',
      ...props,
    },
  };
}

export function contactSection(
  props: Partial<PublicContactSection['props']> = {},
): PublicContactSection {
  return {
    id: 'contact-main',
    type: 'contact',
    props: {
      heading: 'Find us',
      address_lines: ['12 Main Street', 'Buffalo, NY 14201'],
      phone: '(716) 555-0100',
      email: 'hello@example.com',
      ...props,
    },
  };
}

export function gallerySection(
  props: Partial<PublicGallerySection['props']> = {},
): PublicGallerySection {
  return {
    id: 'gallery-main',
    type: 'gallery',
    props: {
      heading: 'Gallery',
      images: [
        imageFixture(),
        imageFixture({
          alt_text: null,
          url: '/api/v1/public/media/00000000-0000-0000-0000-00000000bbbb/w1280',
          variants: [],
        }),
      ],
      ...props,
    },
  };
}

export function menuItemFixture(
  overrides: Partial<PublicMenuItem> = {},
): PublicMenuItem {
  return {
    id: '00000000-0000-0000-0000-000000000101',
    name: 'House roast chicken',
    description: 'Served with seasonal vegetables',
    price_minor: 1250,
    is_available: true,
    is_orderable: true,
    dietary_tags: ['halal'],
    image: null,
    modifier_groups: [],
    ...overrides,
  };
}

export function publicMenuFixture(
  overrides: Partial<PublicMenu> = {},
): PublicMenu {
  return {
    business: {
      name: 'Corner Kitchen',
      slug: 'corner-kitchen',
      timezone: 'America/New_York',
      currency: 'USD',
    },
    categories: [
      {
        id: '00000000-0000-0000-0000-000000000201',
        name: 'Mains',
        description: 'Hearty plates',
        items: [
          menuItemFixture(),
          menuItemFixture({
            id: '00000000-0000-0000-0000-000000000102',
            name: 'Garden salad',
            description: null,
            price_minor: 995,
            is_available: false,
            dietary_tags: ['vegetarian', 'vegan'],
          }),
        ],
      },
      {
        id: '00000000-0000-0000-0000-000000000202',
        name: 'Drinks',
        description: null,
        items: [
          menuItemFixture({
            id: '00000000-0000-0000-0000-000000000103',
            name: 'Fresh lemonade',
            description: null,
            price_minor: 500,
            dietary_tags: [],
            image: imageFixture(),
          }),
        ],
      },
    ],
    featured_item_ids: ['00000000-0000-0000-0000-000000000101'],
    ...overrides,
  };
}

export function storefrontFixture(
  sections: PublicSection[] = [],
  overrides: Partial<Omit<PublicStorefront, 'sections'>> = {},
): PublicStorefront {
  return {
    business: {
      name: 'Corner Kitchen',
      slug: 'corner-kitchen',
      timezone: 'America/New_York',
      currency: 'USD',
    },
    design_variant: 'classic',
    theme: themeFixture(),
    sections,
    ...overrides,
  };
}

// Complex-script fixtures. Each string must be NFC-stable (asserted by the
// Unicode suite as a precondition) and is chosen for the shaping features
// it exercises, not for meaning.
export const COMPLEX_SCRIPT = {
  // Conjunct cluster (ka + virama + ssa) plus vowel signs.
  bengaliConjunct: 'ক্ষুধা লাগলে আসুন',
  // ZWJ inside a cluster: ra + ZWJ + virama + ya (the র‍্য shape).
  bengaliZwj: 'র‍্যাপ র‍্যাক',
  // ZWNJ preventing a conjunct across a morpheme boundary.
  bengaliZwnj: 'দুর্‌যোগ',
  // Matra-heavy running text with mixed punctuation.
  bengaliBody:
    'আমাদের রান্নাঘরে প্রতিদিন টাটকা খাবার তৈরি হয়।\nসবাইকে স্বাগতম।\n\nদ্বিতীয় অনুচ্ছেদ: বিরিয়ানি, কাবাব, মিষ্টি।',
  // Long unbroken Latin-script name (wrapping stress, no hyphens).
  longLatin:
    'Extraordinarily Long Restaurant Name Stresstest Withaverylongunbrokenwordthatmustwrapsafely',
} as const;
