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

| Read | To learn |
| --- | --- |
| [01_PRODUCT_SCOPE.md](01_PRODUCT_SCOPE.md) | Users, first-release boundary, explicit deferrals |
| [02_ARCHITECTURE.md](02_ARCHITECTURE.md) | System shape, repository design, locked decisions |
| [03_DOMAIN_RULES.md](03_DOMAIN_RULES.md) | Domain boundaries and the business rules each owns |
| [04_SECURITY_AND_TENANCY.md](04_SECURITY_AND_TENANCY.md) | The multi-tenancy contract and security baseline |
| [05_DEVELOPMENT_WORKFLOW.md](05_DEVELOPMENT_WORKFLOW.md) | Toolchain, commands, branching, contribution rules |
| [06_TEST_STRATEGY.md](06_TEST_STRATEGY.md) | Test layers, database policy, quality gates |
| [07_DEPLOYMENT_RUNBOOK.md](07_DEPLOYMENT_RUNBOOK.md) | Future-facing deployment skeleton (not yet operational) |
| [08_ROADMAP.md](08_ROADMAP.md) | Milestones, current status, exit criteria |
| [decisions/](decisions/) | Architecture decision records |

## Current state

The project is in **Milestone 0 — Architecture and Repository Contract**.
The repository deliberately contains documentation, configuration, and
tooling contracts only. There is no application code, no database, and no
runnable service yet; those begin in Milestone 1. If you find application
code in the repository during Milestone 0, that is a defect — report it.

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
