# Restaurant Engine

A multi-tenant SaaS platform for independent restaurants: a premium
server-rendered public storefront per restaurant, a restaurant workspace for
owners and staff, and a platform control center for tenant lifecycle
operations. Initial market: Bengali-owned restaurants in Buffalo, New York.

## Status

**Milestone 1 — Platform foundation: complete (2026-07-15).** Milestone 0
(repository contract) and all of Milestone 1 are done: M1A backend +
PostgreSQL foundation, M1B frontend application shells, and M1C the
generated API client (`packages/api-client`, ADR-009), contract drift gate,
integrated CI matrix, and one-command dev stack. Product-domain behavior
(tenants, menus, orders) begins in Milestone 2, which is not started. See
[docs/08_ROADMAP.md](docs/08_ROADMAP.md).

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
