# Restaurant Engine

A multi-tenant SaaS platform for independent restaurants: a premium
server-rendered public storefront per restaurant, a restaurant workspace for
owners and staff, and a platform control center for tenant lifecycle
operations. Initial market: Bengali-owned restaurants in Buffalo, New York.

## Status

**Milestone 0 — Architecture and Repository Contract.** This repository
currently contains the project's governing documents, handbook, architecture
decision records, and tooling contract. There is intentionally **no
application code yet**; the first runnable components arrive in Milestone 1.
See [docs/08_ROADMAP.md](docs/08_ROADMAP.md).

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
