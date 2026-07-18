# 08 — Roadmap

Summarizes blueprint §19 with the approved Milestone 0/1 boundary correction
(2026-07-14). Each milestone must be demoable, testable, documented, and
mergeable. Do not start the next milestone while exit criteria remain open
unless the exception is recorded.

## Milestone boundary decision (2026-07-14)

Principal architecture review resolved a scope conflict between the governing
documents: **Milestone 0 is the architecture and repository contract only**
(governance, handbook, ADRs, hygiene, tooling and workspace contracts, CI
appropriate to existing files). All runnable components — the FastAPI
application, health endpoints, Docker Compose PostgreSQL, frontend shells,
OpenAPI export and generated client, and application tests — belong to
**Milestone 1**. Both governing documents were amended accordingly in the
initial architecture-contract commit.

## Status

| Milestone                                 | State                        |
| ----------------------------------------- | ---------------------------- |
| M0 — Architecture and repository contract | **Complete** (2026-07-14)    |
| M1 — Platform foundation                  | **Complete** (2026-07-15)    |
| M2 — Identity, tenancy, and onboarding    | **In progress** (2026-07-16) |
| M3 – M8                                   | Not started                  |

## Milestone 2 delivery decision (2026-07-16)

The approved M2 architecture (proposal + revision + final addendum)
subdivides M2 into six independently reviewed sub-milestones, one PR each,
strictly sequential:

| Sub                                           | Scope                                                                                                                                                                                                                     | State                     |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **M2A** — Identity & session core             | users/sessions/audit_events schema; Argon2id; opaque hashed-token sessions; login/logout/session; fail-closed CSRF; uniform-failure backoff; audit recorder; bootstrap CLI (ADR-010)                                      | **Complete** (2026-07-16) |
| **M2B** — Tenancy model & capabilities        | businesses (the tenant aggregate, ADR-012), memberships, capability policies (ADR-011), service-layer authorization, lifecycle + platform endpoints, enriched session view, isolation matrix v1                           | **Complete** (2026-07-17) |
| **M2C** — Tenant resolution & isolation       | parser-level host normalization, two-scope trusted-host policy, direct-subdomain slug resolution, reserved-slug policy, public `site` endpoint, neutral public-failure semantics, consolidated isolation matrix (ADR-013) | **Delivered** (local)     |
| **M2D** — Onboarding, recovery & entitlements | invitations, password-reset tokens, feature entitlements, audit list API                                                                                                                                                  | Not started               |
| **M2E** — Control-center auth UI              | login/session UI, guards, accept-invitation and reset pages, dev proxy                                                                                                                                                    | Not started               |
| **M2F** — Platform UI & E2E                   | platform area UI, deep-import lint hardening, first Playwright journeys + CI e2e job                                                                                                                                      | Not started               |

## Milestone 1 delivery decision (2026-07-14)

Approved subdivision into three independently reviewable sub-milestones:

| Sub-milestone                               | Scope                                                                                                                                                                                               | State                     |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **M1A** — Backend and PostgreSQL foundation | FastAPI factory, settings, correlation IDs, structured logging, error envelope (ADR-008), sync SQLAlchemy core (ADR-007), compose database, Alembic baseline, health probes, backend tests + CI job | **Complete** (2026-07-15) |
| **M1B** — Frontend application shells       | Next.js storefront shell, React/Vite control-center shell, neutral placeholder pages, frontend lint/typecheck/test/build                                                                            | **Complete** (2026-07-15) |
| **M1C** — API contract and CI integration   | Deterministic OpenAPI export, generated TypeScript client + facade (ADR-009), drift check, integrated CI matrix, one-command stack + clean-clone verification                                       | **Complete** (2026-07-15) |

M1A ∥ M1B are independent; M1C depends on both. CI gained the backend job
with M1A (untested application code must not merge); the integrated matrix
lands with M1C.

## Milestone 0 — Architecture and repository contract

**Deliver:** governing documents committed; README and orientation; handbook
docs 00–08; ADR template and bootstrap ADRs (001–006); `.gitattributes`,
`.gitignore`, `.editorconfig`, `.env.example`; runtime and dependency-version
policy; pnpm workspace and root command contract; Python project/tooling
contract; TypeScript/Ruff/ESLint/Prettier/mypy/pytest configuration
baselines; CI skeleton appropriate to existing files; Windows and Linux
workflow; contribution and feature-branch workflow.

**Exit criteria:** architecture and scope are understandable from the
repository; runtime/tool versions and commands are defined; repository
configuration is internally consistent; applicable documentation and
configuration validation passes; no application or product-domain behavior
exists.

## Milestone 1 — Platform foundation

**Deliver:** FastAPI skeleton with `/api/v1`, error envelope, request
correlation IDs, structured settings and logging, `/health/live` and
`/health/ready`; PostgreSQL via Docker Compose; Alembic baseline; Next.js
storefront shell and React control-center shell with neutral placeholder
pages; deterministic OpenAPI export and the generated TypeScript client
pipeline; application smoke tests; production builds; CI expanded to run
them.

**Exit criteria:** production builds succeed; migration runs from an empty
database; API client generation is deterministic; no copied cross-app
contracts; a new developer can start the stack with one documented command
and see the health endpoints.

## Milestone 2 — Identity, tenancy, and onboarding

Secure sessions, users, memberships, capability policies, restaurant
lifecycle, tenant resolution, feature entitlements, onboarding API/UI, audit
foundation. **Exit:** isolation matrix passes; platform admin can onboard;
owner logs in only to assigned restaurant; suspension behaves correctly.

## Milestone 3 — Catalog and media

Categories, items, modifiers, integer money, availability, sorting, featured
policy, safe media adapter/upload, restaurant menu UI, public menu API.
**Exit:** constraints and service rules pass; mobile menu administration
works; cross-tenant media and catalog tests pass.

## Milestone 4 — Storefront composition and publication

Section registry, validated configs, design governance, draft/publish/
history, server-rendered storefront, SEO basics, English/Bengali rendering
verification. **Exit:** invalid config cannot save; published config always
renders; draft is never public; performance/accessibility budgets pass.

## Milestone 5 — Hours and pickup readiness

Weekly hours, exceptions, fulfillment settings, pickup-slot service, hours UI
and storefront display. **Exit:** DST, closure, lead-time, and next-opening
tests pass; public availability derives from structured settings.

## Milestone 6 — Cart and guest pickup ordering

Modifier picker, cart schema/versioning, server price validation, idempotent
checkout, order snapshots, tracking token, transactional outbox,
confirmation. **Exit:** retries do not duplicate; stale items fail
gracefully; totals are authoritative; orders survive menu edits; end-to-end
checkout passes.

## Milestone 7 — Restaurant order operations

Order board, guarded status commands, polling, notifications with user
control, audit timeline, operational filtering. **Exit:** permissions and
state machine pass; concurrent staff actions cannot corrupt state; customer
tracker reflects transitions; mobile/tablet usability verified.

## Milestone 8 — Production hardening and pilot

Production compose, wildcard domains/TLS, backup/restore, monitoring,
alerting, security review, rate limits, MFA for platform admins, runbooks,
pilot onboarding checklist. **Exit:** clean-host deployment and restore drill
succeed; critical Playwright suite passes against staging; no default
secrets; first pilot supportable.

## After pilot evidence

Online payments, delivery, SMS, customer accounts, reservations, custom
domains, billing, multi-location, integrations — each prioritized on
restaurant/customer evidence and opened as an architecture discussion, not an
assumed promise.
