# 02 — Architecture

Summarizes blueprint §§3–6, 12–14, 17. The blueprint is authoritative.

## System shape

A **modular monolith in a monorepo**: one FastAPI backend, one PostgreSQL
database, one server-rendered Next.js storefront, one React control-center
SPA, and shared TypeScript packages. Feature growth happens by domain module,
not by adding services.

```mermaid
flowchart TB
    Customer[Customer browser] --> Storefront[Next.js storefront]
    Staff[Owner and staff browser] --> Control[React control center]
    Operator[Platform operator] --> Control
    Storefront --> API[FastAPI modular monolith]
    Control --> API
    API --> DB[(PostgreSQL)]
    API --> Media[Media adapter]
    API --> Jobs[Transactional outbox]
```

There is **no** Redis, message broker, search engine, Kubernetes, GraphQL, or
service mesh in the initial architecture. The first production topology fits
on one VPS behind Nginx.

## Locked decisions

These are fixed direction (see [decisions/](decisions/) for rationale).
Changing one requires a proposed ADR and architectural approval — never a
silent drift.

1. Modular monolith; extraction only on evidence (ADR-001).
2. pnpm-workspace monorepo with exact-version pinning (ADR-002).
3. Two frontend applications — storefront and control center (ADR-003).
4. FastAPI + Pydantic + SQLAlchemy 2 + Alembic + PostgreSQL backend.
5. Next.js App Router storefront with server rendering.
6. React + TypeScript strict + Vite + React Router control center; TanStack
   Query for server state; React Hook Form for forms.
7. OpenAPI-generated TypeScript API client; no handwritten contract copies
   (ADR-004).
8. Opaque database-backed browser sessions; no tokens in localStorage.
9. Integer minor-unit money everywhere.
10. Media behind a narrow storage adapter (local first, S3-compatible later).
11. Transactional outbox for asynchronous order work; no broker.
12. Polling before SSE/WebSockets.
13. PostgreSQL for integration tests; SQLite only for database-independent
    pure tests (ADR-005).
14. Subdomain-first hosting; custom domains deferred.
15. Row-Level Security deferred pending stable access patterns; isolation via
    tenant-scoped repositories, constraints, and permanent tests.

## Architecture principles

- **Tenant safety before convenience** — tenant identity explicit from HTTP
  request to database query; see
  [04_SECURITY_AND_TENANCY.md](04_SECURITY_AND_TENANCY.md).
- **Routers translate; services orchestrate; repositories persist.** HTTP
  routers contain no workflows or persistence. Application services own
  business transactions; repositories never commit.
- **Database constraints are part of the design** — Pydantic/React validation
  improves experience; constraints protect invariants.
- **Make invalid states hard to represent** — enums and state machines for
  status; snapshots for history; integer money.
- **Simple operations are a feature** — every added service must have a
  concrete current use.
- **Generated contracts prevent drift** — OpenAPI is the API contract.
- **Accessibility, security, observability are acceptance criteria**, not
  cleanup milestones.
- **Optimize for reversible decisions** — adapters at volatile boundaries;
  no speculative abstraction inside stable domains.
- **Documentation is executable context** — updated in the same change that
  alters behavior.

## Repository design

```text
restaurant-engine/
├── apps/
│   ├── storefront/                 # Next.js public experience (from M1)
│   └── control-center/             # business + platform admin (from M1)
├── packages/
│   ├── api-client/                 # generated client; never hand-edited (from M1)
│   ├── admin-ui/                   # shared operational components (when consumed)
│   ├── design-tokens/              # color/spacing/typography contracts (when consumed)
│   └── frontend-config/            # shared TS/ESLint/Prettier config (when consumed)
├── backend/
│   ├── app/
│   │   ├── core/                   # settings, database, security, tenancy, errors
│   │   ├── domains/                # identity, businesses, catalog, storefront,
│   │   │                           # media, hours, orders, audit
│   │   ├── api/                    # composition and shared HTTP concerns
│   │   └── main.py
│   ├── migrations/
│   ├── tests/                      # unit / integration / api / security
│   └── pyproject.toml
├── e2e/                            # Playwright journeys + lifecycle owner (M2F)
├── docs/                           # this handbook + decisions/
├── scripts/                        # repeatable developer and ops commands
└── .github/workflows/
```

This tree is a direction, not permission to create empty folders. A directory
appears when its first real contents do. As of Milestone 1C: `backend/app/`
contains `core/`, `api/`, and `main.py` plus `migrations/`, `scripts/`, and
`tests/` (M1A/M1C); `apps/storefront` (Next.js App Router) and
`apps/control-center` (React + Vite + React Router) are the two application
shells (M1B); `packages/api-client` is the generated API client behind its
handwritten facade (M1C, ADR-009); root `scripts/` holds the contract-check
and dev-stack smoke scripts. `backend/app/domains/` appears with the first
domain in Milestone 2.

**API contract flow (M1C, ADR-009):** the backend exports a canonical
OpenAPI document (`packages/api-client/openapi.json`); `openapi-typescript`
generates pure types from it; a handwritten facade over `openapi-fetch` is
the package's only public surface. Both artifacts are committed, produced
only by `corepack pnpm generate:client`, and byte-compared against a fresh
temp-directory regeneration by `corepack pnpm contract:check` locally and in
CI. Operation IDs are explicit contracts, validated at application
composition time. Applications consume only the facade — the first real
consumers, and with them the CORS origin decision, arrive in Milestone 2.

**Control-center API consumption (M2E, ADR-015):** the control center is
the facade's first application consumer, with an origin-relative base URL
(`/api/...` under the page origin). Development uses a same-origin Vite
proxy to the API; production serves both behind one reverse-proxy origin.
The deferred CORS decision is thereby resolved: **no CORS middleware
exists** — there is no cross-origin surface. Session state lives solely
in a TanStack Query cache (opaque cookie session + in-memory CSRF token,
ADR-010/ADR-015).

**Control-center business workspace (M3E, ADR-018):** authenticated routes
are `/businesses/:businessId/...` — the blueprint's earlier
`/restaurants/:restaurantId/...` sketch predates ADR-012's rename of the
tenant aggregate and was amended. The current business is derived from the
route, never held in state, so the switcher in the chrome and the workspace
below it cannot disagree; the switcher lists only `session.memberships`, and
guards there (as everywhere) are navigation aids while the API stays the
authorization boundary. Forms use React Hook Form with a Zod resolver, and
Zod validates UI shape only — required, trimmed, length, decimal precision —
because API truth stays generated from OpenAPI (ADR-004). Shared primitives
(dialog, fields, notifications, failure classification) live in
`apps/control-center/src/components` and `src/api`; no `admin-ui` package
exists, since the bar remains a second real _application_ consumer.

**Storefront domain (M4A–M4C, ADR-020):** `backend/app/domains/storefront`
owns the code-owned section and design-variant registries, the versioned
composition contract, and `storefront_versions` — the single table holding
every draft, published, and archived composition. It references catalog
items and media assets by id and copies neither: a storefront renders the
_current_ menu, while immutable transactional snapshots belong to Orders
(M6). Composition uses optimistic concurrency (`lock_version`) where
catalog uses row locks — a deliberate asymmetry, because a composition edit
is a long-lived session and a catalog edit is not. M4B added the
administrative surface over the M4A foundation: the tenant-scoped
repository and service (draft create/update with §10 media claiming,
publication, archived-only restore, history reads), the platform
design-assignment command, three storefront capabilities
(`business.view` is deliberately insufficient for any storefront read),
three audited actions, and the seven-operation contract — every mutation
behind the capability → Business-`FOR UPDATE` → lifecycle preamble, with
stale writes as 409s carrying the current `lock_version`. M4C added the
public read path: the host-resolved public projection of the current
**published** version, computed per request with no persisted read model
or cache store; the authenticated draft preview over the same assembler;
the §10 public-media predicate extension (public-catalog **or**
enabled-published-section reference); and centrally assigned
route-identity caching (`public, max-age=60` on successful public
storefront responses only — errors and preview stay `no-store`).

**Server-rendered storefront (M4D, ADR-021 — delivered 2026-07-29):**
`apps/storefront` renders
the published composition at `/` and the complete public menu at `/menu`
— fully dynamic request-time SSR, server components only, both routes
gated on the published version and answering the one neutral 404 for
every ineligible host. The server reads the backend through the
api-client facade over a `node:http` tenant transport that forwards the
incoming Host verbatim and is structurally outside Next's URL-keyed data
cache (tenant-cache isolation, ADR-013); `STOREFRONT_API_ORIGIN` is read
at request time with a development default and production fail-closed.
Section renderers and the `classic` design-variant layout dispatch
exhaustively over the generated contract; media renders as native
responsive `<img>` from the delivered renditions; metadata, canonical
origins (deterministic scheme policy), per-host robots/sitemap, and the
audited JSON-LD boundary derive from published data only; storefront HTML
is `no-store` while hashed build assets stay immutable. First-load
JavaScript is budget-enforced in CI (`pnpm storefront:budget`), and
`pnpm storefront:verify` asserts the built server's wire behavior against
a disposable stub API.

**Control-center storefront workspace and shared renderer (M4E, ADR-022 —
delivered 2026-07-30):** the control center gains the storefront
workspace as four deep-linkable full pages under the keyed business
boundary — `/businesses/:businessId/storefront` (overview and draft
composer), `.../storefront/preview`, `.../storefront/history`, and
`.../storefront/history/:versionId`. The M4D renderer's framework-neutral
visual surface moved to **`packages/storefront-renderer`** (section
renderers and exhaustive dispatch, the `classic` variant layout, the
responsive image component, the public menu listing, the pure helpers,
their scoped stylesheets, and the tenant-page baseline under a
zero-specificity `:where()` scope), consumed as raw TypeScript source by
both applications — so the authenticated saved-draft preview renders
through exactly the public components, never a parallel renderer.
`apps/storefront` keeps public transport and Host resolution, SSR, data
loading, metadata/canonical origins, SEO routes, the audited JSON-LD
boundary, and lifecycle/error behavior; public links stay active while
the preview's in-site navigation is structurally inert (the renderer's
one `links: 'active' | 'inert'` prop renders the same anchors without
`href`, so no navigation path exists and no link role is announced).
Workspace affordances derive from role **and** lifecycle: owner and
manager read/edit/preview/history, publish and restore are owner-only,
staff hold no storefront read (no navigation; a deep link gets an honest
denial), and a closed business stays fully readable with every mutation
withheld while provisioning/suspended businesses keep service-authorized
mutations. The 66-operation backend contract, database schema, OpenAPI
document, and generated client are unchanged; the api-client change is
facade-only (the index re-exports the M4C projection types).

**End-to-end verification and Milestone 4 close-out (M4F, ADR-023 —
delivered 2026-07-30):** the E2E lifecycle owner starts the storefront
dev server as its third tracked child (backend → storefront → control
center, port 3100 on loopback, answering 200-or-404 readiness for the
storefront only), and the Playwright suite carries the complete
storefront journeys: mandatory journeys 2 and 3, the cross-host
published-versus-draft contract with archived-only restoration and
suspension/reactivation, responsive acceptance for `classic` across six
viewports on both public routes, and blocking browser accessibility
verification (zero axe violations across eight page/states in the WCAG
2.0/2.1 A/AA rule boundary — engineering evidence, not certification).
M4F changed no production runtime or CI workflow file; with it,
**Milestone 4 is complete** (docs/08). M4G (curated storefront design
and motion) is a proposed future slice recorded in ADR-023, subject to
its own roadmap reconciliation and authorization.

**Frontend workspace conventions (M1B):** one root ESLint flat config and one
root `tsconfig.base.json` own shared configuration as plain files — a shared
package (`frontend-config`, `design-tokens`, `admin-ui`) is created only when
a real consumer exists in the same milestone. Apps never import from each
other. Styling is CSS custom properties + CSS Modules per app (no runtime
styling dependency). Dependency build scripts are blocked by default;
allowances live in `pnpm-workspace.yaml` and are individually reviewed.

### Backend domain module template

A mature domain may contain `models.py`, `schemas.py`, `repository.py`,
`service.py`, `policies.py`, `router_admin.py`, `router_public.py`,
`entities.py`, and `events.py` — but starts with only `models`, `schemas`,
`service`, `repository`, and the necessary router. Split a file when it has
multiple reasons to change.

### Dependency direction

HTTP → application services → domain policies / repository protocols →
SQLAlchemy. Core infrastructure never imports routers. A domain never imports
another domain's SQLAlchemy models to implement hidden logic; cross-domain
writes are coordinated by an application service in one transaction.

## API design

`/api/v1` from the start. Query resources are separated from workflow
commands (`POST .../orders/{id}/accept`, not a generic status PATCH).
Conventions: consistent error envelope with machine-readable code and
correlation ID; UTC ISO-8601 timestamps; integer minor-unit money with
currency; idempotency keys for order placement; explicit request/response
schemas (never serialized ORM objects). See blueprint §10.

## Deployment target (context only until Milestone 8)

One Ubuntu VPS running Docker Compose: Nginx, storefront, API,
control-center static assets, PostgreSQL on a private network with a
persistent volume, a worker once the outbox exists, and an encrypted backup
job. Wildcard subdomain DNS and certificate. Only ports 80/443 public. See
[07_DEPLOYMENT_RUNBOOK.md](07_DEPLOYMENT_RUNBOOK.md).
