# Restaurant Engine

A multi-tenant SaaS platform for independent restaurants: a premium
server-rendered public storefront per restaurant, a restaurant workspace for
owners and staff, and a platform control center for tenant lifecycle
operations. Initial market: Bengali-owned restaurants in Buffalo, New York.

## Status

**Milestone 2 — Identity, tenancy, and onboarding: complete (2026-07-19).**
Milestones 0–2 are done and merged: the repository contract (M0); the
platform foundation — backend + PostgreSQL, frontend shells, generated API
client and contract drift gate (M1, ADR-007–009); and identity, tenancy,
and onboarding — sessions and CSRF, the Business tenant aggregate and
capability authorization, tenant resolution, invitations/recovery/
entitlements, the control-center auth and platform UIs, and the Playwright
E2E foundation (M2, ADR-010–016). **Milestone 3 — Catalog and media** is in
progress as gated sub-milestones (M3A first: catalog core backend,
ADR-017). See [docs/08_ROADMAP.md](docs/08_ROADMAP.md).

## Quick start

```powershell
corepack pnpm install          # workspace dependencies
cd backend; uv sync; cd ..     # backend environment (Python 3.12 via uv)
Copy-Item .env.example .env    # local configuration (safe defaults)
corepack pnpm dev              # database + API + both shells
corepack pnpm smoke:dev        # in a second terminal: verify everything serves
```

API health at `http://127.0.0.1:8000/health/ready`, storefront at
`http://localhost:3000`, control center at `http://localhost:5173`.

## Governing documents

| Document                                                               | Role                                                           |
| ---------------------------------------------------------------------- | -------------------------------------------------------------- |
| [00_RESTAURANT_ENGINE_BLUEPRINT.md](00_RESTAURANT_ENGINE_BLUEPRINT.md) | Architecture and delivery blueprint — the authoritative design |
| [CLAUDE_PROJECT_PROMPT.md](CLAUDE_PROJECT_PROMPT.md)                   | Working agreement for AI-assisted implementation               |

When the handbook and the blueprint disagree, the blueprint wins; raise the
conflict rather than working around it.

## Start here

1. [docs/00_PROJECT_START.md](docs/00_PROJECT_START.md) — orientation and reading order.
2. [docs/01_PRODUCT_SCOPE.md](docs/01_PRODUCT_SCOPE.md) — what we are and are not building.
3. [docs/02_ARCHITECTURE.md](docs/02_ARCHITECTURE.md) — system shape and locked decisions.
4. [docs/05_DEVELOPMENT_WORKFLOW.md](docs/05_DEVELOPMENT_WORKFLOW.md) — toolchain, commands, and contribution workflow.

## Repository layout

```text
restaurant-engine/
├── 00_RESTAURANT_ENGINE_BLUEPRINT.md   # governing blueprint
├── CLAUDE_PROJECT_PROMPT.md            # governing working agreement
├── docs/                               # project handbook + ADRs
├── backend/                            # FastAPI backend (app, migrations, tests, scripts)
├── apps/                               # storefront + control-center shells
├── packages/api-client/                # generated API client + handwritten facade (ADR-009)
├── scripts/                            # contract drift check, dev-stack smoke
└── .github/workflows/                  # CI (repository contract, backend, frontend, contract)
```
