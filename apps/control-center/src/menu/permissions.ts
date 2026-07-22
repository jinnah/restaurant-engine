import type { MembershipSummary } from '@restaurant-engine/api-client';

/**
 * What the current member can be *offered*, derived from role and lifecycle.
 *
 * Every one of these is a navigation and usability aid, never a security
 * decision (docs/02): the service checks the capability and the business
 * lifecycle on every request, and a 403 or 409 that arrives anyway is
 * rendered honestly rather than treated as impossible.
 *
 * The mapping mirrors ADR-017 ruling D4:
 *  - `business.catalog.write` — owner, manager: categories, items,
 *    modifiers, images.
 *  - `business.catalog.availability` — owner, manager, **staff**: the
 *    sold-out toggle, and nothing else. Staff hold no modifier authority of
 *    any kind (M3B).
 *  - `business.media.write` — owner, manager: upload and delete.
 *  - reads use `business.view`, which every role has.
 *
 * Lifecycle: provisioning, active, and suspended businesses are
 * administrable; a closed business is immutable.
 */
export interface MenuPermissions {
  /** Create, edit, delete, reorder, attach images. */
  canWriteCatalog: boolean;
  /** Toggle "sold out today" — the one staff-reachable mutation. */
  canSetAvailability: boolean;
  /** Upload and delete media assets. */
  canWriteMedia: boolean;
  /** The business is closed: everything is read-only, whatever the role. */
  isReadOnly: boolean;
}

export function menuPermissions(
  membership: MembershipSummary,
): MenuPermissions {
  const closed = membership.business_status === 'closed';
  const manages = membership.role === 'owner' || membership.role === 'manager';
  return {
    canWriteCatalog: manages && !closed,
    canSetAvailability: !closed,
    canWriteMedia: manages && !closed,
    isReadOnly: closed,
  };
}
