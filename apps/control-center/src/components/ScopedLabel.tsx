/**
 * The accessible name for a row action, scoped to what it acts on.
 *
 * Row actions must be distinguishable out of context — a list of eight
 * buttons all called "Delete" is unusable by voice control or by a screen
 * reader's element list. Putting the scope in the *visible* label solves
 * that but wrecks the layout, because category, item, and option names are
 * long and user-supplied.
 *
 * So the visible label stays short and the accessible name carries the
 * scope, via `aria-label` rather than visually-hidden text: the accessible
 * name algorithm concatenates child text without a separator, which silently
 * produces names like "EditChutney".
 */
export function scopedLabel(action: string, scope: string): string {
  return `${action} ${scope}`;
}
