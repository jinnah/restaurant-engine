# ADR-006: Tooling baseline and version-pinning policy

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

Milestone 0 must fix the toolchain contract before any application code
exists, so every later milestone works inside known versions and identical
checks locally and in CI. Development happens on Windows (PowerShell) while
CI and production are Linux, so cross-platform behavior and line endings are
first-class concerns, not afterthoughts.

## Decision

- **Node.js 24.x**, with **pnpm pinned exactly** via Corepack's
  `packageManager` field — no global pnpm installs.
- **Python** managed with **uv**: exact dependency versions in
  `backend/pyproject.toml`, locked in `backend/uv.lock`. The Python minor
  version is pinned to 3.12 (`requires-python = ">=3.12,<3.13"`).
- **Formatting/linting:** Prettier and ESLint (flat config) for
  JavaScript/TypeScript and repository documents; Ruff for Python lint and
  format; mypy for Python types; strict TypeScript via a shared
  `tsconfig.base.json`.
- **Exact versions everywhere** — no `^`/`~` ranges; upgrades are small,
  dedicated, reviewed pull requests.
- **LF line endings** enforced repository-wide by `.gitattributes`
  (overriding local `core.autocrlf`), with `.editorconfig` aligning editors.
- **Commands are real:** a script exists only when it genuinely runs against
  files that exist; fake-success placeholders are prohibited. Future
  canonical command names are documented in docs/05 and gain executable
  scripts with their first real consumers.
- **CI (GitHub Actions)** runs exactly the documented commands — the local
  gate and the CI gate are the same list.

## Alternatives considered

- **Floating/caret versions:** rejected — non-reproducible builds and CI.
- **Global pnpm via npm:** rejected — unpinned, per-machine drift.
- **pip/venv or Poetry:** uv chosen for speed, single-tool lock+sync, and
  first-class Windows support.
- **Black/Flake8/isort:** Ruff replaces all three with one pinned tool.

## Consequences

New contributors run `corepack enable && pnpm install` (plus `uv sync` once
the Python contract lands) and get the exact toolchain. Every tool upgrade is
a visible diff. Windows/Linux parity must be checked when adding scripts.

## Security and operations impact

Reproducible, pinned toolchains narrow supply-chain exposure and make
dependency scanning actionable. No credentials exist in CI during
Milestone 0.

## Reconsideration triggers

A pinned tool blocking a needed security update (upgrade immediately via the
normal PR path); build-time pain justifying task orchestration; uv or
Corepack ceasing to be maintained.
