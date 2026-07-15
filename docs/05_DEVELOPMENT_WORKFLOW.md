# 05 — Development Workflow

## Runtime and tool versions

Exact versions are locked in configuration files; this table states the
policy. Upgrades happen intentionally through small, dedicated pull requests
— never by coding against floating `latest`.

| Tool | Policy | Locked where |
| --- | --- | --- |
| Node.js | 24.x | `package.json` `engines` |
| pnpm | Exact version via Corepack | `package.json` `packageManager` |
| Python | Exact minor version, pending final pin (see note) | `backend/pyproject.toml` `requires-python` |
| uv | Python dependency resolution and lockfile | `backend/uv.lock` (arrives with the Python contract) |
| npm dependencies | Exact versions, no ranges | `package.json` + `pnpm-lock.yaml` |
| Python dependencies | Exact versions | `backend/pyproject.toml` + `backend/uv.lock` |

> **Note (Milestone 0):** the Python minor-version pin is an open decision —
> Python 3.12 is preferred but was not installed on the primary development
> machine at contract time. `backend/pyproject.toml` and `backend/uv.lock`
> land as soon as the pin is decided; the decision is tracked in
> [08_ROADMAP.md](08_ROADMAP.md).

## Toolchain setup

### Windows (PowerShell)

```powershell
corepack enable                    # activates the pinned pnpm
pnpm install                       # workspace dev tooling
```

### Linux / macOS

```bash
corepack enable
pnpm install
```

Python setup (uv) is documented here when the Python contract lands:
`uv sync` inside `backend/`.

All repository scripts must work on both Windows PowerShell and Linux.
Platform-specific commands are documented explicitly when unavoidable.

## Command contract

Commands are defined at the repository root and run with `pnpm <script>`.
**A script exists only when it genuinely runs against files that exist.**
Fake-success placeholders are prohibited.

### Executable now (Milestone 0)

| Command | Purpose |
| --- | --- |
| `pnpm format:check` | Prettier verification of docs and configuration |
| `pnpm format` | Apply Prettier formatting |
| `pnpm lint` | ESLint over the JavaScript/TypeScript files that exist |

### Reserved canonical names (first consumers arrive in Milestone 1+)

| Command | Future purpose |
| --- | --- |
| `pnpm typecheck` | Strict TypeScript across all apps/packages |
| `pnpm test` | Frontend unit tests (Vitest) |
| `pnpm build` | Production builds of both applications |
| `pnpm generate:client` | Regenerate the OpenAPI TypeScript client |
| `uv run ruff check` / `uv run pytest` / `uv run mypy app` | Backend lint, tests, types (inside `backend/`) |

Adding one of these scripts requires its real consumer in the same change.

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
