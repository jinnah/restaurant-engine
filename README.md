# Restaurant Engine

A multi-tenant SaaS platform for independent restaurants: a premium
server-rendered public storefront per restaurant, a restaurant workspace for
owners and staff, and a platform control center for tenant lifecycle
operations. Initial market: Bengali-owned restaurants in Buffalo, New York.

## Status

**Milestone 1 — Platform foundation (in progress).** Milestone 0 (repository
contract) and M1A (backend + PostgreSQL foundation: FastAPI skeleton, health
probes, error envelope, Alembic baseline) are complete. M1B adds the two
frontend application shells; M1C adds the generated API client and the
integrated CI/contract pipeline. Product-domain behavior (tenants, menus,
orders) begins in Milestone 2. See [docs/08_ROADMAP.md](docs/08_ROADMAP.md).

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
├── backend/                            # Python project (contract only until M1)
├── apps/                               # storefront + control-center (from M1)
├── packages/                           # shared frontend packages (from M1)
└── .github/workflows/                  # CI
```

`apps/` and `packages/` are declared in the workspace contract but are
intentionally empty until Milestone 1 delivers their first real contents.
