import type { DietaryTag } from '@restaurant-engine/api-client';

/**
 * The dietary registry, as runtime values.
 *
 * ADR-004 prohibits handwritten frontend copies of backend enums "unless
 * they are display-only mappings backed by generated values". This is that
 * exception, and the backing is real rather than nominal: the contract now
 * publishes `DietaryTag` (the M3E fidelity correction), so both directions
 * are checked at compile time.
 *
 * `satisfies` catches a value listed here that the contract does not have.
 * The `Missing` check catches the opposite and more dangerous case — a tag
 * added backend-side that this list does not offer. That one matters
 * because `dietary_tags` is replaced wholesale on update: a UI that cannot
 * render a tag would silently strip it from the next save. Adding a tag to
 * the registry now fails `pnpm typecheck` until the UI is updated.
 *
 * A runtime iterable is unavoidable here: openapi-typescript emits type-only
 * string unions, so the generated artifact can validate this list but cannot
 * be this list.
 */
export const DIETARY_TAGS = [
  'halal',
  'vegetarian',
  'vegan',
] as const satisfies readonly DietaryTag[];

type Missing = Exclude<DietaryTag, (typeof DIETARY_TAGS)[number]>;
// Fails to compile when the contract gains a tag this list does not offer.
const _everyTagIsOffered: [Missing] extends [never] ? true : never = true;
void _everyTagIsOffered;

/** Display labels — presentation only, keyed by the generated union. */
const LABELS: Record<DietaryTag, string> = {
  halal: 'Halal',
  vegetarian: 'Vegetarian',
  vegan: 'Vegan',
};

export function dietaryLabel(tag: DietaryTag): string {
  return LABELS[tag];
}
