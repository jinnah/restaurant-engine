// Exhaustiveness guard (ADR-021). Every dispatch over a closed contract
// union (section types, design variants, hero actions) ends in this call,
// so a contract extension the renderer does not yet handle fails the
// strict typecheck at the switch — and, if drift ever reaches runtime
// (a stale deployment against a newer API), throws into the generic error
// boundary instead of rendering something wrong. The message is bounded
// and value-free: nothing from the payload leaks into logs or responses.

export function assertNever(value: never): never {
  void value;
  throw new Error('unhandled contract variant reached the renderer');
}
