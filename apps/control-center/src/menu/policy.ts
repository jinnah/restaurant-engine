/**
 * Client-side bounds that exist only to help someone typing.
 *
 * The server is the authority for every governed limit, and this module is
 * deliberately almost empty: a limit is mirrored here only when the client
 * must act on it *before* a request exists, and only when doing so cannot
 * present a hand-copied number as though the contract supplied it.
 *
 * The featured ceiling used to live here and no longer does. It is a count
 * enforced in the catalog service, which JSON Schema cannot express, so the
 * generated contract carries no trace of it — a mirrored constant would have
 * been an unverifiable number displayed with the authority of a published
 * one, and would have gone stale silently because no request has to fail for
 * a *displayed* ceiling to be read. The featured limit is now learned solely
 * from a 409's `details.limit`, and until the server states it, no number is
 * shown.
 */

/**
 * The largest price the schema accepts, mirroring
 * `catalog.policies.MAX_PRICE_MINOR` (ADR-017 ruling F1: 0 to 10,000,000
 * minor units inclusive, enforced by the schemas and by named database
 * CHECKs).
 *
 * Unlike the featured ceiling this one is genuinely needed client-side and is
 * safe to hold: `parseMajorToMinor` must classify what the user typed before
 * any request is built, so that "that price is higher than this system
 * allows" can be said next to the field rather than after a round trip. It is
 * advisory in the strict sense — it can only ever *reject* input the server
 * would also reject, it is never displayed as a published limit, and the
 * server's 422 remains the final authority on any value that reaches it. If
 * the backend bound were raised, the worst outcome is a locally rejected
 * price that the server would have accepted; nothing invalid is ever let
 * through, and nothing false is ever displayed.
 */
export const MAX_PRICE_MINOR_DISPLAY = 10_000_000;
