# 00 — Project Start

Welcome to **Restaurant Engine**, a multi-tenant SaaS platform for
independent restaurants. This page is the entry point for every developer,
reviewer, and AI coding agent.

## What this project is

One business system with three user experiences:

1. **Customer storefront** — a premium, server-rendered, indexable public
   site per restaurant (Next.js).
2. **Restaurant workspace** — operational administration for owners,
   managers, and staff (React control center).
3. **Platform control center** — tenant onboarding, entitlements, and
   lifecycle operations for platform operators (same React application,
   permission-gated).

Initial market: Bengali-owned restaurants in Buffalo, New York, then selected
restaurants in New York City. English-first and Bengali-capable, USD,
America/New_York defaults — without baking market specifics into core logic.

## Governing documents

- **[00_RESTAURANT_ENGINE_BLUEPRINT.md](../00_RESTAURANT_ENGINE_BLUEPRINT.md)**
  — the authoritative architecture and delivery blueprint. Every handbook
  page summarizes it; the blueprint wins on conflict.
- **[CLAUDE_PROJECT_PROMPT.md](../CLAUDE_PROJECT_PROMPT.md)** — the working
  agreement governing AI-assisted implementation, including current milestone
  authorization.

## Reading order

| Read                                                     | To learn                                                |
| -------------------------------------------------------- | ------------------------------------------------------- |
| [01_PRODUCT_SCOPE.md](01_PRODUCT_SCOPE.md)               | Users, first-release boundary, explicit deferrals       |
| [02_ARCHITECTURE.md](02_ARCHITECTURE.md)                 | System shape, repository design, locked decisions       |
| [03_DOMAIN_RULES.md](03_DOMAIN_RULES.md)                 | Domain boundaries and the business rules each owns      |
| [04_SECURITY_AND_TENANCY.md](04_SECURITY_AND_TENANCY.md) | The multi-tenancy contract and security baseline        |
| [05_DEVELOPMENT_WORKFLOW.md](05_DEVELOPMENT_WORKFLOW.md) | Toolchain, commands, branching, contribution rules      |
| [06_TEST_STRATEGY.md](06_TEST_STRATEGY.md)               | Test layers, database policy, quality gates             |
| [07_DEPLOYMENT_RUNBOOK.md](07_DEPLOYMENT_RUNBOOK.md)     | Future-facing deployment skeleton (not yet operational) |
| [08_ROADMAP.md](08_ROADMAP.md)                           | Milestones, current status, exit criteria               |
| [decisions/](decisions/)                                 | Architecture decision records                           |

## Current state

Milestones 0 and 1 are **complete** (2026-07-15); Milestone 2 (identity,
tenancy, and onboarding) is **in progress** under the approved M2
architecture — six sub-milestones, one PR each (see
[08_ROADMAP.md](08_ROADMAP.md)). **M2A** (identity and session core,
ADR-010) is delivered: users/sessions/audit tables, Argon2id passwords,
opaque database-backed sessions in HttpOnly cookies, fail-closed CSRF,
uniform login failures with per-account backoff, an append-only audit
recorder, and the `create_platform_admin` bootstrap CLI. The permanent
`tests/security/` suite guards these contracts.

One documented command starts the whole development stack —
`corepack pnpm dev`, which migrates the database before starting any
application process — and `corepack pnpm smoke:dev` proves the health
endpoints and both shells are serving. The OpenAPI document is the API
contract: the generated TypeScript client lives in `packages/api-client`
(ADR-009), regenerated with `corepack pnpm generate:client` and
drift-checked in CI. Tenants, menus, and orders arrive with their
milestones; the first real client consumers (and the same-origin/CORS
decision, ADR-012) arrive at M2C–M2E.

## Rules for AI coding agents

Agents working in this repository must follow
[CLAUDE_PROJECT_PROMPT.md](../CLAUDE_PROJECT_PROMPT.md) in full. In brief:

- read this handbook and the blueprint before planning;
- plan before implementing; state assumptions explicitly;
- work only within the currently authorized milestone;
- never invent requirements, conceal failures, or suppress checks;
- never commit, push, merge, deploy, or delete data without explicit
  authorization;
- update documentation and ADRs in the same change that alters behavior.
