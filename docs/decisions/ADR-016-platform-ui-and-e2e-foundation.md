# ADR-016: Platform Administration UI and End-to-End Testing Foundation

- **Status:** Proposed (M2F in progress; finalized with the M2F delivery)
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

This ADR is completed in the same milestone: sections below are filled
in as the corresponding slices land, and the status moves to Accepted
with the M2F review.

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
tokens extend the ADR-014/015 hygiene to the issuing side: a shared
ephemeral reveal component renders the token exactly once from the
mutation response, never from a refetch, and never lets it reach
URLs, history, storage, query keys, logs, or analytics.

### 4. E2E lifecycle: one orchestrator, one disposable database

_Finalized with the E2E slice; the accepted addendum is binding:_
top-level `e2e/` workspace; `@playwright/test` as the only new
dependency; Chromium, one worker, `fullyParallel: false`, zero
retries; a single cross-platform Node orchestrator (`pnpm e2e`) owning
ports 8100/5273, database recreation, CLI admin bootstrap, child
processes, readiness, Playwright execution, and guaranteed cleanup —
Playwright `webServer`/`globalSetup` deliberately unused; the only
disposable database is `restaurant_engine_e2e`, enforced by an exact
allowlist in the reset script; per-spec independent namespaces with
API fixtures that authenticate legitimately.

### 5. Deep-import hardening completes the roadmap item

The facade-only import restriction (ADR-009, landed for `apps/**` in
M1C) is extended to `e2e/**`. E2E tests are black-box: they interact
through rendered UI and documented HTTP, importing no application or
backend implementation modules.

## Consequences

_To be completed with the delivery: verification evidence, artifact
sensitivity policy, and the manual-smoke decision (deliberately left
pending independent review)._
