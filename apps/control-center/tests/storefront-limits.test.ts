// @vitest-environment node

// The E-6/ADR-022 §7 pin: the ONLY mirrored storefront bounds are the two
// the committed OpenAPI document publishes (`maxItems`). This test reads
// the committed contract artifact at build time — drift between the
// mirror and the contract fails CI instead of silently letting the client
// override the server. Text-length bounds are deliberately absent from
// limits.ts: the contract does not publish them.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';
import {
  MAX_ADDRESS_LINES,
  MAX_GALLERY_IMAGES,
} from '../src/storefront/limits';
import {
  DEFAULT_ACCENT,
  DEFAULT_PALETTE,
  DEFAULT_TYPE_PAIRING,
} from '../src/storefront/composition';

interface SchemaProperty {
  maxItems?: number;
  maxLength?: number;
  default?: unknown;
}

const document = JSON.parse(
  readFileSync(
    join(__dirname, '..', '..', '..', 'packages', 'api-client', 'openapi.json'),
    'utf-8',
  ),
) as {
  components: {
    schemas: Record<string, { properties?: Record<string, SchemaProperty> }>;
  };
};

describe('mirrored bounds equal the committed OpenAPI constraints', () => {
  test('address lines: ContactProps.address_lines maxItems', () => {
    expect(
      document.components.schemas['ContactProps']?.properties?.['address_lines']
        ?.maxItems,
    ).toBe(MAX_ADDRESS_LINES);
  });

  test('gallery images: GalleryProps.images maxItems', () => {
    expect(
      document.components.schemas['GalleryProps']?.properties?.['images']
        ?.maxItems,
    ).toBe(MAX_GALLERY_IMAGES);
  });

  // M4G-A: the composer's create path must state the theme defaults,
  // because the generated `Theme` makes every defaulted field required.
  // They are contract facts, so they are pinned like the bounds above
  // rather than trusted to stay in step with the backend registries.
  test('theme defaults: Theme.{accent,palette,type_pairing} defaults', () => {
    const theme = document.components.schemas['Theme']?.properties;
    expect(theme?.['accent']?.default).toBe(DEFAULT_ACCENT);
    expect(theme?.['palette']?.default).toBe(DEFAULT_PALETTE);
    expect(theme?.['type_pairing']?.default).toBe(DEFAULT_TYPE_PAIRING);
  });

  test('no text-length bound is published for the mirror to claim', () => {
    // If a future contract change publishes these (the recorded ADR-022
    // candidate), this test fails deliberately: the mirror policy must be
    // revisited rather than silently staying narrower than the contract.
    for (const [schema, property] of [
      ['HeroProps', 'heading'],
      ['StoryProps', 'body'],
      ['MenuProps', 'heading'],
    ] as const) {
      expect(
        document.components.schemas[schema]?.properties?.[property]?.maxLength,
      ).toBeUndefined();
    }
  });
});
