import type { MembershipSummary } from '@restaurant-engine/api-client';

/**
 * What the current member can be *offered* on the storefront surface,
 * derived from role AND business lifecycle (ADR-022 §5; ADR-020 §7).
 *
 * Every derivation is a navigation and usability aid, never a security
 * decision: the service checks the capability and lifecycle on every
 * request, and a 403 or 409 that arrives anyway is rendered honestly.
 *
 *  - `business.storefront.read` — owner, manager. Staff hold no storefront
 *    read at all (`business.view` is deliberately insufficient), so staff
 *    see no Storefront navigation and a deep link explains the denial.
 *  - `business.storefront.write` — owner, manager.
 *  - `business.storefront.publish` — owner only; covers restore.
 *
 * Lifecycle: a closed business stays fully READABLE (overview, preview,
 * history, detail) but accepts no mutation; provisioning and suspended
 * businesses keep every mutation the service allows.
 */
export interface StorefrontPermissions {
  /** Overview, saved-draft preview, history, and version detail. */
  canRead: boolean;
  /** Edit and save the draft (including staging media references). */
  canEdit: boolean;
  /** Publish the saved draft (owner only). */
  canPublish: boolean;
  /** Restore an archived version into the draft (owner only). */
  canRestore: boolean;
  /** The business is closed: readable, but every mutation is withheld. */
  isReadOnly: boolean;
}

export function storefrontPermissions(
  membership: MembershipSummary,
): StorefrontPermissions {
  const closed = membership.business_status === 'closed';
  const manages = membership.role === 'owner' || membership.role === 'manager';
  const owns = membership.role === 'owner';
  return {
    canRead: manages,
    canEdit: manages && !closed,
    canPublish: owns && !closed,
    canRestore: owns && !closed,
    isReadOnly: closed,
  };
}
