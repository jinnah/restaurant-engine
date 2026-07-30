// @vitest-environment node

// Deterministic canonical-scheme policy (ADR-021): http exactly for the
// local development host family, https for every public host, port
// preserved, no forwarded-header input by construction (the function
// takes only the validated Host).

import { describe, expect, test } from 'vitest';

import { canonicalOrigin } from '../lib/canonical';

describe('canonicalOrigin', () => {
  test('development host family is http, port preserved', () => {
    expect(canonicalOrigin('localhost')).toBe('http://localhost');
    expect(canonicalOrigin('tandoor.localhost:3000')).toBe(
      'http://tandoor.localhost:3000',
    );
    expect(canonicalOrigin('127.0.0.1:8000')).toBe('http://127.0.0.1:8000');
  });

  test('public hosts are https', () => {
    expect(canonicalOrigin('tandoor.example.com')).toBe(
      'https://tandoor.example.com',
    );
    expect(canonicalOrigin('Tandoor.Example.com')).toBe(
      'https://tandoor.example.com',
    );
    expect(canonicalOrigin('tandoor.example.com:8443')).toBe(
      'https://tandoor.example.com:8443',
    );
  });

  test('a lookalike of the local family is not local', () => {
    expect(canonicalOrigin('evillocalhost')).toBe('https://evillocalhost');
    expect(canonicalOrigin('localhost.example.com')).toBe(
      'https://localhost.example.com',
    );
  });

  test('a malformed host yields no canonical at all', () => {
    expect(canonicalOrigin('')).toBeNull();
    expect(canonicalOrigin('host with spaces')).toBeNull();
    expect(canonicalOrigin('host:port:extra')).toBeNull();
    expect(canonicalOrigin('user@host')).toBeNull();
    expect(canonicalOrigin('[::1]:8000')).toBeNull();
    expect(canonicalOrigin('-leading.example.com')).toBeNull();
  });
});
