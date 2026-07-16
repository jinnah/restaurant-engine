# 05 — Development Workflow

## Runtime and tool versions

Exact versions are locked in configuration files; this table states the
policy. Upgrades happen intentionally through small, dedicated pull requests
— never by coding against floating `latest`.

| Tool                | Policy                                    | Locked where                                 |
| ------------------- | ----------------------------------------- | -------------------------------------------- |
| Node.js             | 24.x                                      | `package.json` `engines`                     |
| pnpm                | Exact version via Corepack                | `package.json` `packageManager`              |
| Python              | 3.12.x (`>=3.12,<3.13`)                   | `backend/pyproject.toml` `requires-python`   |
| uv                  | Python dependency resolution and lockfile | `backend/uv.lock`                            |
| npm dependencies    | Exact versions, no ranges                 | `package.json` + `pnpm-lock.yaml`            |
| Python dependencies | Exact versions                            | `backend/pyproject.toml` + `backend/uv.lock` |

## Toolchain setup

### Windows (PowerShell)

```powershell
corepack enable                    # activates the pinned pnpm globally;
                                   # needs an elevated shell once when Node
                                   # is installed under C:\Program Files
pnpm install                       # workspace dev tooling
```

Without elevation, prefix commands with `corepack` instead — for example
`corepack pnpm install`, `corepack pnpm format:check`. Both forms use the
exact pnpm version pinned in `package.json`.

### Linux / macOS

```bash
corepack enable
pnpm install
```

Python setup (both platforms): run `uv sync` inside `backend/` — it creates
`backend/.venv` on Python 3.12 with the exact locked tool versions. Run
backend tools through uv, for example `uv run ruff check .`.

All repository scripts must work on both Windows PowerShell and Linux.
Platform-specific commands are documented explicitly when unavoidable.

## Development database

PostgreSQL runs in Docker Compose (`compose.yaml` at the repository root).
It listens on host port **5433** because an unrelated native PostgreSQL
service occupies 5432 on the primary development machine.

```powershell
docker compose up -d db      # start (first run pulls the pinned image)
docker compose stop db       # stop; data persists in the named volume
```

Connection values live in `.env.example`; copy to `.env` for local use.

## Command contract

Commands are defined at the repository root and run with `pnpm <script>`.
**A script exists only when it genuinely runs against files that exist.**
Fake-success placeholders are prohibited.

### Repository-wide (from the root)

| Command                | Purpose                                                             |
| ---------------------- | ------------------------------------------------------------------- |
| `pnpm format:check`    | Prettier verification of docs, configuration, and code              |
| `pnpm format`          | Apply Prettier formatting                                           |
| `pnpm lint`            | Root ESLint flat config over the whole workspace                    |
| `pnpm typecheck`       | Strict TypeScript (`tsc --noEmit`) in every workspace package       |
| `pnpm test`            | Unit tests (Vitest) in every workspace package                      |
| `pnpm build`           | Production builds of both applications (needs zero env)             |
| `pnpm generate:client` | Regenerate the two committed API-contract artifacts (ADR-009)       |
| `pnpm contract:check`  | Drift check: temp-dir regeneration byte-compared vs committed files |
| `pnpm dev`             | One-command dev stack: database + API + both shells                 |
| `pnpm smoke:dev`       | Verify the running dev stack (health probes + both shells)          |

The `typecheck`/`test`/`build` scripts shell out through `corepack pnpm -r`
so the pinned pnpm resolves even where Corepack was never globally enabled
(the Windows elevation gotcha above).

### Backend (run inside `backend/`, from Milestone 1A)

| Command                                        | Purpose                                                    |
| ---------------------------------------------- | ---------------------------------------------------------- |
| `uv run uvicorn app.main:create_app --factory` | Run the API (add `--reload` for development)               |
| `uv run pytest`                                | Full backend suite (needs the compose database)            |
| `uv run pytest -m "not integration"`           | Unit and API tests only — no database required             |
| `uv run pytest -m integration`                 | PostgreSQL-backed tests only                               |
| `uv run ruff check .` / `uv run ruff format .` | Lint / format Python                                       |
| `uv run mypy app tests`                        | Strict type check                                          |
| `uv run alembic upgrade head`                  | Apply migrations to the database in `DATABASE_URL`         |
| `uv run alembic revision -m "..."`             | Create a migration (ruff hooks format it; review the diff) |

Integration tests **fail with a clear message** (never skip) when the
database is down — start it with `docker compose up -d db` first. The API
serves `/health/live`, `/health/ready`, and (non-production) `/docs`.

### Frontend development (from Milestone 1B)

| Command                                                   | Purpose                                   |
| --------------------------------------------------------- | ----------------------------------------- |
| `pnpm --filter @restaurant-engine/storefront dev`         | Next.js dev server (port 3000)            |
| `pnpm --filter @restaurant-engine/control-center dev`     | Vite dev server (port 5173)               |
| `pnpm --filter @restaurant-engine/storefront start`       | Serve the storefront production build     |
| `pnpm --filter @restaurant-engine/control-center preview` | Serve the control-center production build |

Environment-variable conventions (no frontend variables exist yet): values
exposed to browser code use the framework prefixes `NEXT_PUBLIC_*`
(storefront) and `VITE_*` (control center); every new variable gets a safe
placeholder in `.env.example` in the same change that consumes it. The M1B
shells build with **zero** environment variables. Dev-server URLs print as
`localhost`; note the database's 127.0.0.1 rule above applies only to
PostgreSQL connections.

### One-command development stack (from Milestone 1C)

`corepack pnpm dev` starts everything, in a strict sequence:

1. the compose database (`docker compose up -d --wait db`, idempotent —
   blocks until the healthcheck passes);
2. `alembic upgrade head` against that database, so a clean or outdated
   database is migrated **before** any application process exists — a
   migration failure aborts the command and nothing starts;
3. the API via uvicorn on **127.0.0.1:8000**, the storefront on **3000**,
   and the control center on **5173**, with prefixed output under
   `concurrently`.

Stopping it (Ctrl+C) tears down all three processes; only the database
container keeps running (stop it with `docker compose stop db`).
Prerequisites — all of them, nothing hidden:

1. Docker Desktop running;
2. `corepack pnpm install` at the root;
3. `uv sync` inside `backend/`;
4. `.env` copied from `.env.example` (backend `DATABASE_URL`; the shells
   need zero environment variables).

`corepack pnpm smoke:dev` (run in a second terminal) polls
`/health/live`, `/health/ready`, and both shells with a bounded timeout and
exits 0 only when everything serves. The shells are checked via
`localhost` — Vite binds the loopback family `localhost` resolves to — while
the 127.0.0.1 rule above is specific to PostgreSQL connections.

### API contract pipeline (from Milestone 1C, ADR-009)

The OpenAPI document is the API contract. Two committed, generated artifacts
— `packages/api-client/openapi.json` and
`packages/api-client/src/generated/schema.ts` — are produced **only** by
`corepack pnpm generate:client` and never hand-edited (Prettier/ESLint
ignore exactly these two paths). `corepack pnpm contract:check` regenerates
both into a temporary directory and byte-compares against the committed
files without touching the repository; CI runs the identical command.

Rules:

- **Operation IDs are contracts.** Every schema-visible route declares an
  explicit `operation_id`; `create_app` refuses to compose otherwise.
  Renaming a Python handler never changes the contract; renaming an
  `operation_id` is a breaking change and needs a deliberate, reviewed
  decision.
- A pull request that changes API surface must include the matching
  regenerated artifacts (the backend test suite and the contract job both
  fail otherwise). A generated-only diff without a backend change is
  rejected.
- Applications import **only** `@restaurant-engine/api-client` (the facade);
  deep imports of generated modules fail module resolution and lint.

## Git workflow

- Default branch: `main`. Never commit directly to `main` after the initial
  architecture contract; all work goes through feature branches.
- Branch naming: `feature/<milestone-or-topic>`, e.g.
  `feature/m0-repository-contract`.
- Small, logical commits with imperative messages; a commit leaves the
  repository coherent (docs, config, and code agree).
- Merges happen through reviewed pull requests once a remote exists; merging,
  pushing, and remote creation are owner actions unless explicitly delegated.
- Line endings: LF everywhere, enforced by `.gitattributes` (which overrides
  any local `core.autocrlf`). Editors follow `.editorconfig`.

## Change sequence (blueprint §20.1)

1. Clarify behavior and constraints.
2. Review applicable handbook sections and ADRs.
3. Write a short implementation plan with files, contracts, risks, tests.
4. Review architecture before coding when a boundary or schema changes.
5. Create a focused feature branch.
6. Implement in vertical slices.
7. Run local targeted tests continuously.
8. Review the diff for tenant scope, security, transactions, errors, docs.
9. Run the full relevant quality gate.
10. Open a pull request with evidence and migration/deployment notes.
11. Merge only after review and green CI.
12. Deploy through the release process and smoke test (from Milestone 8).

## Definition of done (blueprint §20.3)

A feature is done when acceptance behavior is met; authorization and tenant
scoping are explicit; invariants exist in service logic **and** database
constraints; tests at the right levels pass; API/client contracts are
synchronized; loading, empty, error, and mobile states are handled;
accessibility is reviewed; logs/audit/metrics are adequate; migrations and
rollback implications are documented; documentation is current.

## Environment files

Copy `.env.example` to `.env` for local values. `.env` is gitignored and
never committed. Every new variable is added to `.env.example` with a safe
placeholder in the same change that consumes it.

## AI-assisted development

Agents follow [CLAUDE_PROJECT_PROMPT.md](../CLAUDE_PROJECT_PROMPT.md): plan
first when requested, state assumptions, stay within the authorized
milestone, report results honestly, and never commit, push, merge, deploy,
or delete data without explicit authorization.
