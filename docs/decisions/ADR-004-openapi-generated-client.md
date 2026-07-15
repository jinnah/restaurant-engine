# ADR-004: OpenAPI-generated TypeScript API client

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

The predecessor prototype hand-wrote `api.ts` files and duplicated backend
enums and interfaces in each frontend, synchronized by comments. Drift
between backend contracts and frontend types was caught only at runtime or
in review.

## Decision

The FastAPI **OpenAPI document is the API contract**. A TypeScript client
package (`packages/api-client`) is generated from it deterministically, plus
a thin handwritten facade for ergonomic call sites. Generated files are never
hand-edited. CI verifies that regeneration produces no unexplained diff.
Handwritten frontend copies of backend enums are prohibited unless they are
display-only mappings backed by generated values.

## Alternatives considered

- **Handwritten client (prototype):** rejected by direct drift experience.
- **GraphQL with codegen:** rejected — typed REST resources and commands
  serve the use cases without a new query layer (blueprint §5.1).
- **Sharing Pydantic-derived types via a custom bridge:** rejected — OpenAPI
  is the standard, tool-supported boundary.

## Consequences

Backend schema changes surface as compile-time diffs in every consumer. The
export must be deterministic (stable ordering, LF, pinned generator) or the
drift check produces noise — this determinism is a Milestone 1 acceptance
criterion. Zod remains only for UI-specific form concerns.

## Security and operations impact

Contract review happens in one artifact; accidental exposure of new fields
becomes a visible generated-code diff in review.

## Reconsideration triggers

The generator producing unusable output for a needed OpenAPI feature;
adoption of an API style OpenAPI cannot express.
