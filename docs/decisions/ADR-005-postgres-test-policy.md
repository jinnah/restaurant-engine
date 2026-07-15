# ADR-005: PostgreSQL integration tests; limited SQLite use

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

The predecessor prototype ran its entire backend suite on in-memory SQLite.
That made tests fast and hermetic, but the production database is
PostgreSQL: composite foreign keys, check constraints, JSONB behavior,
transaction isolation, and locking semantics differ. The architecture
(blueprint §3.4) makes database constraints a primary integrity boundary —
so tests that bypass the real database bypass the design.

## Decision

Integration, API, and security/tenancy tests that depend on constraints,
transactions, JSONB, or locking run against **PostgreSQL** — locally via the
Docker Compose database (from Milestone 1) and in CI via a service
container, with migrations applied rather than ORM `create_all`. SQLite is
permitted **only** for pure tests whose behavior is database-independent.
Tests use isolated databases/schemas and deterministic factories.

## Alternatives considered

- **SQLite everywhere (prototype):** rejected — cannot exercise the
  constraints the architecture relies on; false confidence.
- **PostgreSQL for everything including pure unit tests:** rejected — wastes
  feedback speed where the database is irrelevant.
- **Testcontainers-style per-test containers:** deferred — Compose service
  reuse is simpler on the current single-developer topology.

## Consequences

Running the full backend suite requires Docker locally. Domain unit tests
stay fast and dependency-free. CI gains a postgres service container in
Milestone 1.

## Security and operations impact

The tenant-isolation test matrix (docs/04) exercises real composite
constraints — isolation claims rest on the same engine that enforces them in
production.

## Reconsideration triggers

Suite runtime harming feedback loops (parallel schemas or transactional
rollback fixtures first); a managed-Postgres feature gap between local and
production versions.
