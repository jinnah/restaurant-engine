// Composition adapters (ADR-022 §4): section-id shape and uniqueness for
// new sections (E-10), exact round-tripping, and the D-5 serialization
// intents.

import type { StorefrontConfig } from '@restaurant-engine/api-client';
import { describe, expect, test } from 'vitest';
import {
  composerValuesFromConfig,
  defaultSectionValues,
  DEFAULT_ACCENT,
  DEFAULT_PALETTE,
  DEFAULT_TYPE_PAIRING,
  SECTION_TYPES,
  toDraftPut,
} from '../src/storefront/composition';
import { storefrontConfig } from './support/mockClient';

// The backend's SECTION_ID_PATTERN (storefront.policies): a stable ASCII
// slug the owner never sees.
const SECTION_ID_PATTERN = /^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$/;

describe('new section ids (E-10)', () => {
  test('every generated id is its type name, a valid slug, and unique', () => {
    const ids = SECTION_TYPES.map((type) => defaultSectionValues(type).id);
    for (const [index, id] of ids.entries()) {
      expect(id).toBe(SECTION_TYPES[index]);
      expect(id).toMatch(SECTION_ID_PATTERN);
    }
    expect(new Set(ids).size).toBe(ids.length);
  });

  test('seeds fabricate no content: text fields start empty', () => {
    const hero = defaultSectionValues('hero');
    expect(hero.type === 'hero' && hero.props.heading).toBe('');
    const story = defaultSectionValues('story');
    expect(story.type === 'story' && story.props.body).toBe('');
  });

  test('the hours seed is presentation-only (M5D, ADR-025 D5)', () => {
    // No schedule field exists to seed: the section carries a heading, an
    // optional intro, and the status-line toggle, and nothing else.
    const hours = defaultSectionValues('hours');
    expect(hours).toEqual({
      id: 'hours',
      type: 'hours',
      enabled: true,
      props: { heading: '', intro: null, show_open_now: true },
    });
  });
});

describe('round-tripping', () => {
  test('existing ids and section order pass through serialization unchanged', () => {
    const config = storefrontConfig({
      sections: [
        {
          id: 'story-original',
          type: 'story',
          enabled: false,
          props: { heading: 'Ours', body: 'Body.' },
        },
        {
          id: 'hero-main',
          type: 'hero',
          enabled: true,
          props: {
            heading: 'Hi',
            subheading: null,
            image: null,
            primary_action: 'view_menu',
          },
        },
      ],
      theme: { accent: '#123abc', palette: 'warm', type_pairing: 'humanist' },
    });
    const values = composerValuesFromConfig(config);
    const body = toDraftPut(values, 7);
    expect(body.config.sections?.map((section) => section.id)).toEqual([
      'story-original',
      'hero-main',
    ]);
    expect(body.config.theme?.accent).toBe('#123abc');
    expect(body.expected_lock_version).toBe(7);
  });

  test('create intent OMITS expected_lock_version (never a guessed 0)', () => {
    const body = toDraftPut(composerValuesFromConfig(null), null);
    expect('expected_lock_version' in body).toBe(false);
    expect(body.config.schema_version).toBe(1);
    expect(body.config.sections).toEqual([]);
  });

  test('the form model is a deep copy: editing it never mutates the cache', () => {
    const config = storefrontConfig({
      sections: [
        {
          id: 'menu',
          type: 'menu',
          enabled: true,
          props: { heading: 'Menu', intro: null },
        },
      ],
    });
    const values = composerValuesFromConfig(config);
    const section = values.sections[0];
    if (section?.type === 'menu') {
      section.props.heading = 'Mutated';
    }
    expect(config.sections?.[0]?.props.heading).toBe('Menu');
  });
});

// M4G-A. The draft PUT is a full-document replacement (ADR-020 D-5), so a
// theme field the composer does not re-send is reset to its schema default
// by the next ordinary save. The composer edits only the accent; palette,
// typography pairing, and the logo belong to controls that do not exist
// yet (M4G-C), and an owner renaming a section must not silently discard
// them.
describe('theme preservation through an unrelated save', () => {
  const LOGO_ID = '9f1d2c3b-4a5e-4f60-8b71-2c3d4e5f6a7b';

  function savedWith(theme: NonNullable<StorefrontConfig['theme']>) {
    const config = storefrontConfig({
      theme,
      sections: [
        {
          id: 'story',
          type: 'story',
          enabled: true,
          props: { heading: 'Ours', body: 'Body.' },
        },
      ],
    });
    // An edit that has nothing to do with the theme.
    const values = composerValuesFromConfig(config);
    const section = values.sections[0];
    if (section?.type === 'story') {
      section.props.heading = 'Renamed';
    }
    return toDraftPut(values, 3).config.theme;
  }

  test('a non-default palette survives', () => {
    expect(
      savedWith({
        accent: '#a34b2a',
        palette: 'midnight',
        type_pairing: 'humanist',
      })?.palette,
    ).toBe('midnight');
  });

  test('a non-default type pairing survives', () => {
    expect(
      savedWith({
        accent: '#a34b2a',
        palette: 'warm',
        type_pairing: 'serif_display',
      })?.type_pairing,
    ).toBe('serif_display');
  });

  test('an existing theme logo survives', () => {
    expect(
      savedWith({
        accent: '#a34b2a',
        palette: 'warm',
        type_pairing: 'humanist',
        logo: { media_id: LOGO_ID },
      })?.logo,
    ).toEqual({ media_id: LOGO_ID });
  });

  test('editing the accent preserves every other theme field', () => {
    const config = storefrontConfig({
      theme: {
        accent: '#a34b2a',
        palette: 'olive',
        type_pairing: 'geometric',
        logo: { media_id: LOGO_ID },
      },
    });
    const values = composerValuesFromConfig(config);
    values.accent = '#0055ff';

    expect(toDraftPut(values, 3).config.theme).toEqual({
      accent: '#0055ff',
      palette: 'olive',
      type_pairing: 'geometric',
      logo: { media_id: LOGO_ID },
    });
  });

  test('a legacy configuration carrying only an accent still works', () => {
    // Parsed off the wire on purpose: the generated `Theme` marks every
    // defaulted field required, so a bare theme cannot be written as a
    // typed literal — yet it is exactly what a server predating M4G-A (or
    // any future contract drift) would send. The adapter must not crash on
    // it, and the accent it *was* given must survive untouched.
    //
    // The three absent fields come back as the registry defaults rather
    // than staying absent, and that is the M4G-C consequence of owning
    // them: the composer now offers a control for each, so it states the
    // value each control is showing. Those are exactly the values the
    // server applies to an omitted field, so the stored configuration is
    // identical either way — nothing is fabricated and no stored choice is
    // overwritten.
    const legacy = JSON.parse(
      '{"schema_version":1,"theme":{"accent":"#123abc"},"sections":[]}',
    ) as StorefrontConfig;

    const body = toDraftPut(composerValuesFromConfig(legacy), 2);

    expect(body.config.theme).toEqual({
      accent: '#123abc',
      palette: DEFAULT_PALETTE,
      type_pairing: DEFAULT_TYPE_PAIRING,
      logo: null,
    });
    expect(body.expected_lock_version).toBe(2);
  });

  test('the create path states the platform defaults explicitly', () => {
    // Nothing is stored to carry, and the generated `Theme` makes every
    // defaulted field required. The server would apply the same values.
    expect(
      toDraftPut(composerValuesFromConfig(null), null).config.theme,
    ).toEqual({
      accent: DEFAULT_ACCENT,
      palette: DEFAULT_PALETTE,
      type_pairing: DEFAULT_TYPE_PAIRING,
      logo: null,
    });
  });

  test('the carried theme is a deep copy of the cached config', () => {
    const config = storefrontConfig({
      theme: {
        accent: '#a34b2a',
        palette: 'ember',
        type_pairing: 'humanist',
        logo: { media_id: LOGO_ID },
      },
    });
    const values = composerValuesFromConfig(config);
    values.carriedTheme.palette = 'slate';
    expect(config.theme?.palette).toBe('ember');
  });
});
