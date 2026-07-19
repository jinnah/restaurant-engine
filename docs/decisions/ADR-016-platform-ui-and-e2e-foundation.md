# ADR-016: Platform Administration UI and End-to-End Testing Foundation

- **Status:** Accepted
- **Date:** 2026-07-19
- **Deciders:** Product owner, principal architect

## Context

M2F gives platform administrators their first UI — until now every
platform operation (business provisioning, lifecycle, invitations,
recovery, audit) existed only as M2B/M2D APIs — and introduces the
repository's Playwright end-to-end layer with its process/database
lifecycle. The approved architecture went through a source-grounded
proposal and a binding E2E-lifecycle addendum; the decisions recorded
here are the accepted rulings.

All decisions below were accepted before implementation; the E2E
lifecycle follows the binding architecture addendum verbatim.

## Decisions

### 1. Platform area scope and the entitlements deferral

The platform area delivers business list/create/detail, lifecycle
commands with proportionate confirmation, invitation administration
with one-time token reveal, password-reset issuance, and the platform
audit stream — all against the existing M2B/M2D contracts with **zero
backend, OpenAPI, or generated-client change**.

**Entitlements administration is deliberately absent.** The platform
surface has only the idempotent full-set
`PUT /platform/businesses/{id}/entitlements`; the sole read
(`business_entitlements_get`) requires the `business.view`
_membership_ capability, which platform administrators intentionally
never hold (ADR-011). A write-only UI could silently revoke a
business's current features. Revisit triggers: a second registry key,
the first entitlement enforcement (M6), or a platform business
read-model design — whichever arrives first brings a platform-scope
read API and the UI together.

### 2. Authorization presentation

Platform navigation renders only for `is_platform_admin` users; an
authenticated non-administrator deep-linking `/platform/**` receives
the standard NotFound experience. This is presentation only — the
backend capability checks (403) remain the authority. Anonymous deep
links flow through the existing RequireAuth → sanitized-`next` login
round-trip unchanged.

### 3. Session and security invariants are inherited, not re-decided

The M2E architecture is consumed as-is: one `['session']` TanStack
Query cache, memory-only call-time CSRF, the session-generation guard,
privileged-401 clearing, sanitized internal redirects. Platform
mutations never write session state. Issued invitation and reset
tokens extend the ADR-014/015 hygiene to the issuing side: the
issuance response is handed to the page's transient reveal state
inside the mutation function and the mutation itself **resolves
token-free**, so neither the query cache nor the TanStack mutation
cache ever holds a raw token; the shared ephemeral reveal renders it
exactly once, never from a refetch, and it never reaches URLs,
history, storage, query keys, logs, or analytics.

### 4. E2E lifecycle: one orchestrator, one disposable database

A top-level `e2e/` workspace package carries `@playwright/test`
(exact-pinned; the milestone's only new registry dependency) and runs
Chromium-only, one worker, `fullyParallel: false`, zero retries —
serial for determinism and resource control, never as permission for
order coupling.

One cross-platform Node entry point, `pnpm e2e`
(`e2e/scripts/run-e2e.mjs` over an injectable orchestrator core), owns
the complete lifecycle in order: signal/cleanup registration before any
mutation; a both-loopback preflight of ports 8100 and 5273 that fails
rather than attach to an existing server; recreation of the disposable
`restaurant_engine_e2e` database at the migration head via
`backend/scripts/reset_e2e_database.py`, which hard-refuses — before
opening any connection — every database name except that exact literal
(and drops its own half-made database if migration fails); seeding of
the single universal fixture, a synthetic platform administrator,
through the documented bootstrap CLI with the password on stdin;
spawning and tracking the backend (`DATABASE_URL` constructed by the
orchestrator, never inherited; `TRUSTED_ORIGINS` set to exactly the
browser origin `http://localhost:5273`) and the control center (Vite
strict port 5273, proxy target supplied by `CC_API_PROXY_TARGET`, dev
default unchanged); bounded readiness polls; Playwright with selection
arguments passed through; then termination of only the tracked child
process trees (PID-scoped, never by port or name) and a guaranteed
database drop in the cleanup path shared by success, failure, timeout,
and SIGINT/SIGTERM. A cleanup failure is loudly reported and nonzero
but never replaces the primary result. Playwright's `webServer`,
`globalSetup`, and `globalTeardown` are deliberately unused — one
lifecycle owner; a bare `playwright test` refuses without the
orchestrator's sentinel. The orchestrator's failure paths are
regression-tested (node:test, injected fakes); CI's `e2e` job invokes
the identical `pnpm e2e` with deterministic Chromium installation and
failure-only artifact upload.

Test independence is structural: each spec owns a fixed namespace in
the per-run database and builds its own prerequisites — through the UI
when the setup _is_ the journey (onboarding), through authenticated
API fixtures otherwise (real login, session-derived CSRF, exact
trusted Origin, public invitation acceptance; no raw SQL for domain
data, no bypassed authorization, tokens held in memory only).

### 5. Deep-import hardening completes the roadmap item

The facade-only import restriction (ADR-009, landed for `apps/**` in
M1C) is extended to `e2e/**`. E2E tests are black-box: they interact
through rendered UI and documented HTTP, importing no application or
backend implementation modules.

## Consequences

- Platform administrators onboard businesses entirely through the
  product (M2's exit criterion), with every consequential action
  confirmed proportionately (typed-name confirmation for the terminal
  close) and every issued credential shown exactly once.
- E2E artifacts (traces/screenshots, failure-only, video off) contain
  only synthetic credentials for a database that is dropped after every
  run — and are still treated as sensitive test artifacts: gitignored
  locally, uploaded only on failure in CI with bounded retention.
- Parallel E2E execution (per-worker databases) is a documented later
  step; nothing in the design depends on serial ordering.
- Whether a separate manual browser smoke adds value beyond Playwright
  is deliberately left open until the M2F independent review.
- The entitlements administration UI returns together with a
  platform-scope read API (see decision 1's triggers).
