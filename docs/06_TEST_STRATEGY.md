# 06 — Test Strategy

Summarizes blueprint §15. The blueprint is authoritative.

## Current state (Milestone 0)

**No tests exist yet, and none are faked.** Milestone 0 contains no
application code, so there is nothing to test beyond documentation and
configuration checks (`pnpm format:check`, `pnpm lint`, CI hygiene checks).
The first real tests arrive in Milestone 1 with the first runnable code, and
every milestone after that adds the layers below for the behavior it ships.

## Test layers

| Layer               | Purpose                              | Examples                                            |
| ------------------- | ------------------------------------ | --------------------------------------------------- |
| Domain unit         | Fast business-rule feedback          | Modifier selection, status transitions, pickup time |
| Service integration | Transaction and persistence behavior | Publish state machine, order snapshot, reorder      |
| API                 | Auth, schemas, errors, permissions   | Login, menu commands, platform suspend              |
| Security/tenancy    | Permanent isolation contracts        | Cross-tenant IDs, uploads, cache, membership        |
| Frontend component  | Important interaction behavior       | Modifier form, publish warning, order ticket        |
| End-to-end          | Critical journeys across deployments | Onboard → publish; order → accept → ready           |
| Operational         | Restore and deployment confidence    | Migration on production-like DB, backup restore     |

## Database policy (ADR-005)

PostgreSQL is used for integration and API tests that depend on constraints,
transactions, JSONB, or locking. SQLite may be used **only** for pure tests
whose behavior is database-independent. A production PostgreSQL system does
not claim confidence from an SQLite-only suite. Tests use isolated databases
or schemas and deterministic factories; migrations are applied in CI rather
than relying on ORM table creation.

## Mandatory end-to-end journeys (by first commercial release)

1. Platform admin onboards a restaurant and owner.
2. Owner logs in, creates a menu, uploads an image, edits content, publishes.
3. Public visitor sees only the published version under the correct host.
4. Visitor customizes an item and places one pickup order despite a
   simulated retry.
5. Staff accepts, prepares, and marks the order ready; visitor sees status.
6. Tenant A cannot discover or modify tenant B data through API or UI.
7. Suspended tenant becomes unavailable publicly without data loss.

## Quality gates

A pull request cannot merge unless the checks relevant to its contents pass.
The full gate (from Milestone 1 onward, growing with the codebase):

- Ruff lint and format check; Python type check at the agreed strictness;
- pytest unit/integration/API/security suites;
- ESLint and Prettier; strict TypeScript; frontend unit tests;
- production builds;
- OpenAPI client regeneration produces no unexplained diff;
- migration upgrade from the previous schema succeeds;
- Playwright smoke suite for protected milestone branches;
- dependency/secret scan.

During Milestone 0 the gate is the subset that applies to existing files:
formatting, linting, configuration consistency, and repository hygiene.

Coverage is a diagnostic, not a target substitute: critical state machines
and tenant boundaries require behavior coverage regardless of the global
percentage.
