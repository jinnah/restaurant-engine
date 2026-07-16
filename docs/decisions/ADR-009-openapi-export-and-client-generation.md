# ADR-009: OpenAPI export and TypeScript client generation toolchain

- **Status:** Accepted
- **Date:** 2026-07-15
- **Deciders:** Product owner, principal architect

## Context

ADR-004 decided that the OpenAPI document is the API contract and that a
TypeScript client is generated from it deterministically, with drift checked
in CI. Milestone 1C must choose the concrete toolchain, the artifact
ownership rules, and the enforcement mechanics — before the first product
endpoint exists, because every later domain inherits them.

## Decision

### Canonical export

`backend/scripts/export_openapi.py` renders the FastAPI schema in canonical
form: sorted keys (independent of insertion order), two-space indent, UTF-8,
LF line endings, one trailing newline — byte-identical on every platform.
The export needs no environment, `.env`, or database: settings are explicit
in-code placeholders with implicit sources disabled, and the engine connects
lazily. The committed artifact is `packages/api-client/openapi.json`.

### Operation IDs are contracts

Every schema-visible route declares an explicit `operation_id`
(`health_live`, `health_ready`, …). `create_app` validates presence and
uniqueness at composition time (`app/core/openapi.py`) — a violating process
never starts, so the rule enforces itself for every future route. Renaming a
Python handler can therefore never change the contract silently; changing an
`operation_id` itself is a deliberate, reviewed breaking change that
surfaces as a generated-artifact diff and facade compile errors.

### Generation toolchain

`openapi-typescript` (exact-pinned) generates a single pure-types file,
`packages/api-client/src/generated/schema.ts`, via its Node API
(`packages/api-client/scripts/generate.mjs`) so the committed artifact and
the drift check share one code path. `openapi-fetch` (exact-pinned, ~6 kB,
zero dependencies) provides the typed runtime, wrapped by the handwritten
facade. Generation runs offline against the committed spec.

### Package boundary

`@restaurant-engine/api-client` is a source-only workspace package (no build
step). Its `exports` map exposes **only** `src/index.ts`: the facade
functions and intentionally public types. Public error/response types are
aliases of generated types, never handwritten duplicates. Deep imports of
`src/generated/*` fail module resolution and are additionally forbidden by
lint in `apps/**`. Generated code stays replaceable: a generator swap
touches only the generated directory and internal wiring.

### Ownership and drift enforcement

Both artifacts are committed, generated only by `pnpm generate:client`, and
never hand-edited; Prettier/ESLint exclusions cover exactly those two paths.
Drift is caught in three layers: a backend unit test byte-compares a fresh
in-memory export against the committed spec (fails in plain `uv run
pytest`); `pnpm contract:check` regenerates both artifacts into a temporary
directory, verifies the output contains exactly the expected files,
byte-compares against the committed artifacts, reports which drifted, always
cleans up, and never modifies the repository (so it works from a dirty
tree); CI runs the identical command in the `contract` job. A pull request
that changes API surface must contain the matching regenerated artifacts; a
generated-only diff without a backend change is rejected in review.

## Alternatives considered

- **`@hey-api/openapi-ts` (full client codegen):** solid, but generates a
  much larger runtime surface (service/schema modules) — noisier drift
  diffs and more generated code to own, with no benefit behind a facade.
- **`openapi-generator-cli`:** Java dependency, templated output,
  historically nondeterministic across versions.
- **Orval / RTK-codegen:** couple the contract package to a specific app
  client library; server-state libraries belong in the apps (Milestone 2+),
  layered on the facade.
- **Generate-on-install instead of committing artifacts:** rejected — the
  contract becomes unreviewable and drift is visible only in CI.
- **Whole-worktree `git status` drift check:** rejected — false-fails on
  legitimately dirty trees; replaced by the temp-directory byte-compare.

## Consequences

Backend contract changes surface as reviewable generated diffs and facade
compile errors. The facade is the single translation point, so consumers
(first real ones in Milestone 2, together with the CORS decision) never bind
to generator idioms. Toolchain upgrades are deliberate small PRs whose
regenerated diff is the review artifact.

## Security and operations impact

Codegen runs offline; no schemas are fetched remotely. New dependencies
(`openapi-typescript`, `openapi-fetch`, `concurrently`) are exact-pinned and
run no install scripts (the workspace blocks build scripts by default).
Accidental exposure of new fields becomes a visible generated-code diff in
review (ADR-004). The export script's placeholder DSN is not a credential.

## Reconsideration triggers

The generator producing unusable output for a needed OpenAPI feature;
abandonment of openapi-typescript/openapi-fetch; adoption of an API style
OpenAPI cannot express; facade ergonomics failing under many domains.
