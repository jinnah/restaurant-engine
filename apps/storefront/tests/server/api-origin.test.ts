// @vitest-environment node

import { describe, expect, test } from 'vitest';

import { resolveApiOrigin } from '../../lib/server/api-origin';

describe('resolveApiOrigin', () => {
  test('defaults to the documented local API outside production', () => {
    expect(resolveApiOrigin({ NODE_ENV: 'test' })).toBe(
      'http://127.0.0.1:8000',
    );
    expect(resolveApiOrigin({ NODE_ENV: 'development' })).toBe(
      'http://127.0.0.1:8000',
    );
  });

  test('production fails closed when the variable is missing or empty', () => {
    expect(() => resolveApiOrigin({ NODE_ENV: 'production' })).toThrow(
      /STOREFRONT_API_ORIGIN must be set in production/,
    );
    expect(() =>
      resolveApiOrigin({ NODE_ENV: 'production', STOREFRONT_API_ORIGIN: '' }),
    ).toThrow(/must be set in production/);
  });

  test('accepts a bare http(s) origin and normalizes to the origin', () => {
    expect(
      resolveApiOrigin({
        NODE_ENV: 'production',
        STOREFRONT_API_ORIGIN: 'https://api.internal:8443',
      }),
    ).toBe('https://api.internal:8443');
    expect(
      resolveApiOrigin({
        NODE_ENV: 'test',
        STOREFRONT_API_ORIGIN: 'http://127.0.0.1:8100',
      }),
    ).toBe('http://127.0.0.1:8100');
  });

  test.each([
    'not a url',
    'ftp://example.com',
    'http://example.com/api',
    'http://example.com/?q=1',
    'http://example.com/#frag',
    'http://user:pass@example.com',
  ])('rejects a non-origin value in every environment: %s', (value) => {
    expect(() =>
      resolveApiOrigin({ NODE_ENV: 'test', STOREFRONT_API_ORIGIN: value }),
    ).toThrow(/STOREFRONT_API_ORIGIN/);
    expect(() =>
      resolveApiOrigin({
        NODE_ENV: 'production',
        STOREFRONT_API_ORIGIN: value,
      }),
    ).toThrow(/STOREFRONT_API_ORIGIN/);
  });
});
