// @vitest-environment node

import { describe, expect, test } from 'vitest';

import { mailtoHref, telHref } from '../src/contact-links';

describe('telHref', () => {
  test('derives a dialable tel: from conventional formats', () => {
    expect(telHref('(716) 555-0100')).toBe('tel:7165550100');
    expect(telHref('+1 716 555 0100')).toBe('tel:+17165550100');
    expect(telHref('716.555.0100')).toBe('tel:7165550100');
  });

  test('refuses values without an unambiguous link form', () => {
    expect(telHref('call us after five')).toBeNull();
    expect(telHref('ask for Rob')).toBeNull();
    expect(telHref('++')).toBeNull();
  });
});

describe('mailtoHref', () => {
  test('derives mailto: only for a plain single address', () => {
    expect(mailtoHref('hello@example.com')).toBe('mailto:hello@example.com');
    expect(mailtoHref('front desk')).toBeNull();
    expect(mailtoHref('a b@example.com')).toBeNull();
    expect(mailtoHref('hello@localhost')).toBeNull();
  });
});
