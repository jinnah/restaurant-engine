// Post-authentication landing (item 2): an authorized deep link is honoured,
// an unreachable one resolves to the user's role-appropriate home instead of
// Page Not Found. Pure functions, no rendering.

import { describe, expect, test } from 'vitest';
import { canReachPath, landingPath, roleHomePath } from '../src/auth/landing';
import {
  adminSessionView,
  membership,
  sessionView,
} from './support/mockClient';

const OWNED = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const FOREIGN = '99999999-9999-4999-8999-999999999999';

const owner = sessionView({
  memberships: [membership({ business_id: OWNED })],
});
const admin = adminSessionView();

describe('roleHomePath', () => {
  test('an owner goes home to the dashboard, an admin to the platform area', () => {
    expect(roleHomePath(owner)).toBe('/');
    expect(roleHomePath(admin)).toBe('/platform');
  });
});

describe('canReachPath', () => {
  test('platform routes need a platform administrator', () => {
    expect(canReachPath('/platform', admin)).toBe(true);
    expect(canReachPath('/platform/businesses', admin)).toBe(true);
    expect(canReachPath('/platform', owner)).toBe(false);
    expect(canReachPath('/platform/audit?business=x', owner)).toBe(false);
  });

  test('a workspace needs a membership in that exact business', () => {
    expect(canReachPath(`/businesses/${OWNED}/menu`, owner)).toBe(true);
    expect(canReachPath(`/businesses/${FOREIGN}/menu`, owner)).toBe(false);
    // A platform admin holds no memberships, so no workspace is reachable.
    expect(canReachPath(`/businesses/${OWNED}/menu`, admin)).toBe(false);
  });

  test('the home and other authenticated routes are always reachable', () => {
    expect(canReachPath('/', owner)).toBe(true);
    expect(canReachPath('/', admin)).toBe(true);
    expect(canReachPath('/somewhere?page=2', owner)).toBe(true);
  });
});

describe('landingPath', () => {
  test('a reachable deep link is honoured for both roles', () => {
    expect(landingPath(`/businesses/${OWNED}/menu`, owner)).toBe(
      `/businesses/${OWNED}/menu`,
    );
    expect(landingPath('/platform/businesses', admin)).toBe(
      '/platform/businesses',
    );
    expect(landingPath('/dest?page=2', owner)).toBe('/dest?page=2');
  });

  test('a platform admin following a stale owner deep link lands on the platform home', () => {
    expect(landingPath(`/businesses/${FOREIGN}/menu`, admin)).toBe('/platform');
  });

  test('an owner following a platform link lands on their dashboard', () => {
    expect(landingPath('/platform/businesses', owner)).toBe('/');
  });

  test('an unsafe next sanitizes to "/", which is reachable for either role', () => {
    // "/" is always reachable, so the role-home fallback never applies to it;
    // it applies only to a safe-but-unreachable target (the cases above).
    expect(landingPath('https://evil.example/x', owner)).toBe('/');
    expect(landingPath('//evil.example', admin)).toBe('/');
    expect(landingPath(null, owner)).toBe('/');
  });

  test('no next means the home, reachable for either role', () => {
    expect(landingPath('', owner)).toBe('/');
    expect(landingPath('', admin)).toBe('/');
  });
});
