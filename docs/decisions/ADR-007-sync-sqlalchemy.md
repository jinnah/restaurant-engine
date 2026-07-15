# ADR-007: Sync-first SQLAlchemy with psycopg 3

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

Milestone 1A establishes the database core every later domain builds on.
SQLAlchemy 2 supports both a synchronous API and an asyncio API (asyncpg /
psycopg async), and the choice shapes every service, repository, test
fixture, and transaction boundary after it. The platform targets modest,
one-VPS scale (ADR-001); the team optimizes for learning, debuggability, and
boring correctness over throughput.

## Decision

The backend uses **synchronous SQLAlchemy 2 with the psycopg 3 driver**.
Endpoints that touch the database are plain `def` routes, which FastAPI runs
on its threadpool. The engine uses `pool_pre_ping` and a bounded connect
timeout; sessions come from a request-scoped `get_session` dependency
(`app/core/database.py`). Application services own commit/rollback;
repositories never commit.

## Alternatives considered

- **Async SQLAlchemy (asyncpg or psycopg async):** rejected for now — adds
  greenlet indirection, harder debugging and stack traces, stricter
  discipline around lazy loading and session sharing, and event-loop
  subtleties, in exchange for concurrency headroom the one-VPS topology does
  not need. Alembic and most fixtures remain sync anyway.
- **Mixed mode (async routes, sync DB in threadpool via `run_in_executor`):**
  rejected — the complexity of both models with the benefits of neither.

## Consequences

Services, repositories, and tests stay straightforward to write and reason
about; strict mypy works with the typed sync API today. The session
dependency is the seam: a later move to async is a contained migration of
`app/core/database.py` and its consumers, not a redesign — but it is a
migration, accepted deliberately.

## Security and operations impact

Fewer concurrency failure modes around transactions and tenant-scoped
sessions; connection behavior is bounded and observable (pre-ping, connect
timeout). None negative identified.

## Reconsideration triggers

Measured request concurrency that saturates the threadpool with idle-in-DB
waits; adoption of Server-Sent Events at Milestone 7+ if the polling order
board is replaced; an integration requiring long-lived streaming connections.
