# ADR-002: pnpm workspace monorepo with exact version pinning

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

The platform has multiple frontend surfaces plus shared concerns (generated
API client, admin UI, design tokens, tooling config). The predecessor
prototype kept three separate frontend apps with **hand-copied duplicate
packages** kept in sync by comments — a proven source of drift and wasted
review effort.

## Decision

One repository managed as a **pnpm workspace**: `apps/*` and `packages/*`
plus the Python `backend/`. The pnpm version is pinned through Corepack's
`packageManager` field; all JavaScript dependencies are pinned to exact
versions and locked in `pnpm-lock.yaml`. Python dependencies are locked with
uv (`backend/uv.lock`). Task orchestration (Turborepo/Nx) is deliberately
omitted until build time is a measured problem.

## Alternatives considered

- **Multiple repositories:** rejected — cross-repo contract changes (API →
  client → UI) would need coordinated releases for a one-person team.
- **npm/yarn workspaces:** viable, but pnpm's strict node_modules layout
  catches undeclared dependencies and its Corepack pinning is clean.
- **Copied shared code (prototype approach):** rejected by direct experience.

## Consequences

One change can atomically update API contract, generated client, and UI.
Contributors must have Corepack enable the pinned pnpm rather than a global
install. Version upgrades become explicit, reviewable diffs.

## Security and operations impact

Lockfiles make CI and future production builds reproducible and auditable;
exact pinning narrows supply-chain exposure windows and makes dependency
scanning meaningful.

## Reconsideration triggers

Workspace build times becoming a measured bottleneck (add task
orchestration, not repo splits); a genuinely external consumer of a package
requiring independent publishing.
