/**
 * Permutation helpers for the reorder controls.
 *
 * Pure and total: every function returns a complete permutation of its
 * input, because that is exactly what the reorder contract requires. The
 * server validates the submitted set against the stored set and rejects
 * anything inexact with a 409, so producing a partial or duplicated list
 * here would turn a UI slip into a failed request (ADR-017: reorders are
 * full-set, exact-set-validated, atomic, and no-op-suppressed).
 *
 * An out-of-range move is a no-op rather than an error: pressing "up" on the
 * first row should do nothing, not throw.
 */

export function moveTo<T>(items: readonly T[], from: number, to: number): T[] {
  const next = [...items];
  if (from < 0 || from >= next.length || to < 0 || to >= next.length) {
    return next;
  }
  const [moved] = next.splice(from, 1);
  if (moved === undefined) {
    return [...items];
  }
  next.splice(to, 0, moved);
  return next;
}

export function moveUp<T>(items: readonly T[], index: number): T[] {
  return moveTo(items, index, index - 1);
}

export function moveDown<T>(items: readonly T[], index: number): T[] {
  return moveTo(items, index, index + 1);
}

/** True when two orderings are identical — the server suppresses these. */
export function sameOrder(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}
