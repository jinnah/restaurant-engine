// Composition adapters (ADR-022 §4): section-id shape and uniqueness for
// new sections (E-10), exact round-tripping, and the D-5 serialization
// intents.

import { describe, expect, test } from 'vitest';
import {
  composerValuesFromConfig,
  defaultSectionValues,
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
      theme: { accent: '#123abc' },
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
