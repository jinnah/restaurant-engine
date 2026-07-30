// The verified 422 path grammar and its conversion (ADR-022 §7):
// `body.config.sections.{i}.{tag}.{rest}` with the discriminated-union
// tag AFTER the index, matched by full indexed path — never by field
// name — and dropped only when the tag equals the form's discriminant.

import { describe, expect, test } from 'vitest';
import { ApiFailure } from '../src/api/failure';
import {
  dialogFieldFor,
  mapDraftSaveFailure,
} from '../src/storefront/fieldErrors';
import { envelope } from './support/mockClient';

function failureWith(
  fields: { field: string; code: string; message: string }[],
) {
  return new ApiFailure(
    422,
    envelope('validation_error', 'Request validation failed.', fields),
  );
}

describe('mapDraftSaveFailure', () => {
  test('maps the probed grammar onto exact indexed RHF paths', () => {
    const mapped = mapDraftSaveFailure(
      failureWith([
        {
          field: 'body.config.sections.0.hero.props.heading',
          code: 'value_error',
          message: 'Heading too long.',
        },
        {
          field: 'body.config.sections.2.gallery.props.images.0.alt_text',
          code: 'value_error',
          message: 'Alt text too long.',
        },
        {
          field: 'body.config.theme.accent',
          code: 'value_error',
          message: 'Bad accent.',
        },
      ]),
      ['hero', 'menu', 'gallery'],
    );
    expect(mapped.fields).toEqual([
      { path: 'sections.0.props.heading', message: 'Heading too long.' },
      {
        path: 'sections.2.props.images.0.alt_text',
        message: 'Alt text too long.',
      },
      { path: 'accent', message: 'Bad accent.' },
    ]);
    expect(mapped.unmapped).toEqual([]);
  });

  test('repeated field names cannot collide: matching is by full path', () => {
    const mapped = mapDraftSaveFailure(
      failureWith([
        {
          field: 'body.config.sections.1.story.props.heading',
          code: 'value_error',
          message: 'Story heading.',
        },
      ]),
      ['hero', 'story'],
    );
    // Same trailing name as the hero's heading, but the index and tag pin
    // it to the story section alone.
    expect(mapped.fields).toEqual([
      { path: 'sections.1.props.heading', message: 'Story heading.' },
    ]);
  });

  test('a tag/index mismatch is never guessed onto a field', () => {
    const mapped = mapDraftSaveFailure(
      failureWith([
        {
          field: 'body.config.sections.0.story.props.heading',
          code: 'value_error',
          message: 'Mismatched.',
        },
      ]),
      ['hero'],
    );
    expect(mapped.fields).toEqual([]);
    expect(mapped.unmapped).toEqual(['Mismatched.']);
  });

  test('whole-document and media-reference messages stay in the summary', () => {
    const mapped = mapDraftSaveFailure(
      failureWith([
        {
          field: 'body.config.sections',
          code: 'value_error',
          message: 'At most one section of each type.',
        },
        {
          field: 'body.expected_lock_version',
          code: 'int_parsing',
          message: 'Not an integer.',
        },
      ]),
      ['hero'],
    );
    expect(mapped.fields).toEqual([]);
    expect(mapped.unmapped).toEqual([
      'At most one section of each type.',
      'Not an integer.',
    ]);
  });

  test('an envelope with no field errors surfaces its message', () => {
    const failure = new ApiFailure(
      422,
      envelope('validation_error', 'One media reference is not usable.'),
    );
    const mapped = mapDraftSaveFailure(failure, []);
    expect(mapped.fields).toEqual([]);
    expect(mapped.unmapped).toEqual(['One media reference is not usable.']);
  });
});

describe('dialogFieldFor (section-relative -> dialog fields)', () => {
  test('scalar props map to their dialog fields', () => {
    expect(dialogFieldFor('props.heading')).toBe('heading');
    expect(dialogFieldFor('props.subheading')).toBe('subheading');
    expect(dialogFieldFor('props.primary_action')).toBe('primaryAction');
    expect(dialogFieldFor('props.body')).toBe('body');
    expect(dialogFieldFor('props.intro')).toBe('intro');
    expect(dialogFieldFor('props.phone')).toBe('phone');
    expect(dialogFieldFor('props.email')).toBe('email');
    expect(dialogFieldFor('enabled')).toBe('enabled');
  });

  test('indexed props keep their index', () => {
    expect(dialogFieldFor('props.address_lines.2')).toBe(
      'addressLines.2.value',
    );
    expect(dialogFieldFor('props.images.7.alt_text')).toBe('images.7');
    expect(dialogFieldFor('props.image.media_id')).toBe('image');
  });

  test('unknown paths return null rather than a guess', () => {
    expect(dialogFieldFor('props.unknown_field')).toBeNull();
    expect(dialogFieldFor('id')).toBeNull();
  });
});
