// The role x lifecycle permission matrix (ADR-022 §5; ADR-020 §7). Every
// derivation is presentation only — the service re-checks capability and
// lifecycle on every request — but the offered affordances must mirror
// the contract exactly.

import { describe, expect, test } from 'vitest';
import { storefrontPermissions } from '../src/storefront/permissions';
import { membership } from './support/mockClient';

describe('storefrontPermissions', () => {
  test('owner of an active business: full surface', () => {
    expect(
      storefrontPermissions(
        membership({ role: 'owner', business_status: 'active' }),
      ),
    ).toEqual({
      canRead: true,
      canEdit: true,
      canPublish: true,
      canRestore: true,
      isReadOnly: false,
    });
  });

  test('manager: read and edit, never publish or restore', () => {
    expect(
      storefrontPermissions(
        membership({ role: 'manager', business_status: 'active' }),
      ),
    ).toEqual({
      canRead: true,
      canEdit: true,
      canPublish: false,
      canRestore: false,
      isReadOnly: false,
    });
  });

  test('staff: no storefront surface at all', () => {
    const permissions = storefrontPermissions(
      membership({ role: 'staff', business_status: 'active' }),
    );
    expect(permissions.canRead).toBe(false);
    expect(permissions.canEdit).toBe(false);
    expect(permissions.canPublish).toBe(false);
    expect(permissions.canRestore).toBe(false);
  });

  test('closed business: readable for owner and manager, no mutations', () => {
    for (const role of ['owner', 'manager'] as const) {
      const permissions = storefrontPermissions(
        membership({ role, business_status: 'closed' }),
      );
      expect(permissions.canRead).toBe(true);
      expect(permissions.canEdit).toBe(false);
      expect(permissions.canPublish).toBe(false);
      expect(permissions.canRestore).toBe(false);
      expect(permissions.isReadOnly).toBe(true);
    }
  });

  test('provisioning and suspended businesses keep every allowed mutation', () => {
    for (const status of ['provisioning', 'suspended']) {
      const owner = storefrontPermissions(
        membership({ role: 'owner', business_status: status }),
      );
      expect(owner.canEdit).toBe(true);
      expect(owner.canPublish).toBe(true);
      expect(owner.canRestore).toBe(true);
      expect(owner.isReadOnly).toBe(false);
    }
  });
});
