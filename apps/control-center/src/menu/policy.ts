/**
 * Governed limits, mirrored for display only.
 *
 * These are NOT the authority. Each mirrors a backend product-policy
 * constant so an administrator sees the ceiling before reaching it, rather
 * than discovering it through a failure (ADR-018 ruling 7). The server
 * decides, and every conflict response carries the real number in
 * `details.limit`.
 *
 * When a server limit disagrees with the value here, the UI shows the
 * server's number, refetches, and reports the drift — the constant is never
 * treated as correct against the API.
 */

/**
 * Mirrors `catalog.policies.MAX_FEATURED_ITEMS` (ADR-017 ruling R1: at most
 * six featured items per business, counting hidden ones — hiding an item
 * never clears the flag).
 */
export const FEATURED_LIMIT_DISPLAY = 6;

/**
 * Mirrors `catalog.policies.MAX_PRICE_MINOR` (ADR-017 ruling F1: prices are
 * 0 to 10,000,000 minor units inclusive, enforced by the schemas and by
 * named database CHECKs).
 */
export const MAX_PRICE_MINOR_DISPLAY = 10_000_000;

/** A stable marker so a limit disagreement is greppable in a bug report. */
export const LIMIT_DRIFT_MARKER = '[m3e:limit-drift]';

/**
 * Report a governed limit that the server disagrees with. Visible reporting
 * is the caller's job; this is the diagnostic half.
 */
export function reportLimitDrift(
  limitName: string,
  expected: number,
  serverLimit: number,
): void {
  console.error(
    `${LIMIT_DRIFT_MARKER} ${limitName}: this app expects ${String(expected)}, the server reported ${String(serverLimit)}. The server is authoritative; update the mirrored constant.`,
  );
}
