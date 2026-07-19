import { describe, expect, test } from 'vitest';
import { sanitizeNext } from '../src/auth/redirect';

// Composed via char codes so no escape sequence ambiguity can weaken the
// hostile inputs.
const BACKSLASH = String.fromCharCode(92);
const TAB = String.fromCharCode(9);
const NUL = String.fromCharCode(0);
const DEL = String.fromCharCode(127);

describe('accepted internal paths', () => {
  test.each([
    ['/', '/'],
    ['/businesses', '/businesses'],
    ['/businesses?page=2&sort=name', '/businesses?page=2&sort=name'],
    ['/a/b/c', '/a/b/c'],
  ])('%s -> %s', (input, expected) => {
    expect(sanitizeNext(input)).toBe(expected);
  });

  test('fragments are dropped', () => {
    expect(sanitizeNext('/businesses#section')).toBe('/businesses');
  });

  test('dot segments are normalized before use', () => {
    expect(sanitizeNext('/a/../businesses')).toBe('/businesses');
  });
});

describe('rejected values fall back to /', () => {
  test.each([
    ['empty string', ''],
    ['missing leading slash', 'businesses'],
    ['scheme-relative', '//evil.example'],
    ['absolute URL', 'https://evil.example/x'],
    ['absolute URL without slash prefix', 'http:/evil.example'],
    ['login loop', '/login'],
    ['login loop with trailing slash', '/login/'],
    ['login subpath', '/login/whatever'],
    ['login via dot segments', '/x/../login'],
    ['token query key', '/x?token=abc'],
    ['token-bearing key name', '/x?invite_token=abc'],
    ['case-variant token key', '/x?TOKEN=abc'],
    ['percent-encoded token key', '/x?reset%5Ftoken=abc'],
    ['encoded slash lowercase', '/a%2fb'],
    ['encoded slash uppercase', '/a%2Fb'],
    ['encoded backslash lowercase', '/a%5cb'],
    ['encoded backslash uppercase', '/a%5Cb'],
  ])('%s', (_name, input) => {
    expect(sanitizeNext(input)).toBe('/');
  });

  test.each([
    ['literal backslash', '/a' + BACKSLASH + 'b'],
    ['backslash pair prefix', '/' + BACKSLASH + BACKSLASH + 'evil'],
    ['tab control character', '/a' + TAB + 'b'],
    ['NUL control character', '/a' + NUL],
    ['DEL character', '/a' + DEL],
  ])('%s', (_name, input) => {
    expect(sanitizeNext(input)).toBe('/');
  });

  test('non-string values', () => {
    expect(sanitizeNext(undefined)).toBe('/');
    expect(sanitizeNext(null)).toBe('/');
    expect(sanitizeNext(42)).toBe('/');
    expect(sanitizeNext(['/x'])).toBe('/');
  });

  test('over-length values', () => {
    expect(sanitizeNext('/' + 'a'.repeat(3000))).toBe('/');
  });
});
