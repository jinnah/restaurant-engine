import type { ModifierGroupView } from '@restaurant-engine/api-client';

/**
 * Selection rules and satisfiability, phrased for a restaurant owner.
 *
 * "Required" is not a field: a group is required when `min_select >= 1`
 * (ADR-017 M3B). The UI presents that as a checkbox, but it never invents an
 * `is_required` property the contract does not have.
 *
 * Satisfiability is computed by the server and is strictly report-only —
 * a legal but unsatisfiable configuration is always storable, and nothing
 * here may block a write because of it (ruling D5).
 */
export function ruleSummary(group: {
  min_select: number;
  max_select: number | null;
}): string {
  const { min_select: min, max_select: max } = group;
  if (min === 0) {
    if (max === null) {
      return 'Optional — choose any number';
    }
    return max === 1
      ? 'Optional — choose at most 1'
      : `Optional — choose up to ${String(max)}`;
  }
  if (max === null) {
    return min === 1
      ? 'Required — choose at least 1'
      : `Required — choose at least ${String(min)}`;
  }
  if (min === max) {
    return min === 1
      ? 'Required — choose exactly 1'
      : `Required — choose exactly ${String(min)}`;
  }
  return `Required — choose ${String(min)} to ${String(max)}`;
}

/**
 * Why the server considers a group unsatisfiable, derived from the numbers it
 * already returned. Null when the group is fine.
 *
 * The consequence sentence is truthful about the public menu: an
 * unsatisfiable **required** group makes the item non-orderable, while an
 * unsatisfiable optional group is simply omitted (docs/03, M3D). Neither
 * prevents saving.
 */
export function unsatisfiableReason(group: ModifierGroupView): string | null {
  if (group.is_satisfiable) {
    return null;
  }
  const active = group.active_option_count;
  const consequence =
    group.min_select >= 1
      ? ' Customers cannot order this item until it is resolved.'
      : ' It will be left off your public menu until it is resolved.';

  if (active === 0) {
    return `No options are available in this group.${consequence}`;
  }
  if (group.min_select > active) {
    return `This group asks for at least ${String(group.min_select)} but only ${String(active)} ${active === 1 ? 'option is' : 'options are'} available.${consequence}`;
  }
  return `This group allows up to ${String(group.max_select ?? 0)} but only ${String(active)} ${active === 1 ? 'option is' : 'options are'} available.${consequence}`;
}
