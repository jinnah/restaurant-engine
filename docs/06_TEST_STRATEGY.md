# 06 — Test Strategy

Summarizes blueprint §15. The blueprint is authoritative.

## Current state (Milestone 3F — in progress)

M3F adds the end-to-end coverage for Milestone 3 (ADR-019). It is
implemented and verified locally; the milestone is **not closed**, and
owner acceptance is a gate before it can be.

`pnpm e2e` grows from four journeys to nine tests, still Chromium-only,
one worker, zero retries:

- **The menu vertical slice.** An owner signs in, creates a category and
  two items, uploads and attaches an image, adds a required option group
  and a choice, hides the second item, features the first, reorders, and
  the result appears on the tenant's public surface. Money is proved by
  identity — `12.50` must arrive as exactly `1250` minor units and a
  `1.00` surcharge as exactly `100` — because a shape assertion would pass
  for a floating-point path too. Hidden and sold out are asserted as the
  different things they are: the hidden item is absent from the public
  menu entirely, the sold-out one stays listed with `is_available` and
  `is_orderable` false. The image assertions are chosen so they cannot
  pass vacuously (see the fixture note below).
- **Cross-business isolation.** Two businesses, both built by the spec.
  The decisive assertion is media: business A's image URL is a neutral 404
  under B's host **and** a live 200 under A's, in the same run. A 404 for
  something that does not exist proves nothing; a 404 for something being
  served one host away is the boundary.
- **Tenant-host resolution**, pinned before the journey depends on it, so
  a resolution failure can never present as a menu-administration failure.
- **Phone-width administration** at 375×812 — the blueprint's M3
  acceptance bar, now a project command rather than a documented
  procedure.

Three things about how this suite reads the public surface are worth
naming, because each is a trap that would otherwise be rediscovered:

- **Browser navigation, never `request`.** Playwright's `request` fixture
  runs in the Node driver and uses the OS resolver; Windows does not
  resolve `*.localhost` (measured: `ENOTFOUND`). Chromium resolves the
  `.localhost` TLD itself per RFC 6761. Using `request` would have given a
  suite that passes in CI and fails on a developer machine.
- **Not through the UI origin.** The Vite proxy forwards with
  `changeOrigin: false`, so a proxied request keeps `Host: localhost:5273`
  and resolves to no tenant. A test pins this from the other side.
- **A fresh browser context per public read.** No session cookie, so a
  passing assertion cannot be an artefact of being signed in; and an empty
  HTTP cache, because public media is `max-age=3600, immutable` and a
  warm context would answer "is this still served?" from its own cache.

The image fixture is committed (`e2e/fixtures/menu-item.png`, 800×600) and
its width is load-bearing: variants are generated only strictly narrower
than the canonical, so 800 px yields exactly `w320` and `w640` and no
`w1280`. A smaller fixture would produce none and the responsive-image
assertion would prove nothing.

The E2E stack now owns a disposable **media root** as well as a disposable
database. Both are constructed rather than inherited, both are removed on
success, failure, timeout, and signal, and the development media root is
refused by name — an E2E run cannot touch development data.

Two limits are deliberate. The public surface here is the host-resolved
public **API**, not a rendered storefront: `apps/storefront` is still the
Milestone 1 shell and customer-facing rendering is M4. And the phone-width
coverage is limited engineering evidence about layout and reach at one
width — no accessibility scan runs, and target size, contrast, and focus
order are not assessed, so no conformance claim is made.

The mandatory journeys 2 and 3 below are therefore **partially** satisfied
by M3: everything except publication, published-version semantics, and
storefront composition, which are M4.

## Earlier state (Milestone 3E)

M3E is delivered and merged (PR #15, 2026-07-22, ADR-018). What follows is
the coverage on `main`.

The control center's business workspace is covered by component and
integration tests (Vitest, injected client, the real route table through a
memory router). Four kinds are worth naming:

- **Payload-shape assertions.** Every mutation test asserts the exact
  request the facade received, not just that it was called. That is what
  proves updates send only changed fields — a PATCH that resends an
  unchanged value silently overwrites a concurrent edit under ADR-017 D5's
  last-committed-write semantics — and that a create payload never carries an
  update-only field.
- **Pure utilities tested in isolation.** Money conversion and reorder
  permutations carry no JSX and are tested directly: `0.10` must be exactly
  10 minor units, every stored integer must round-trip through the editable
  form in a two-, zero- and three-decimal currency, and every permutation
  helper must return a complete permutation, because the server validates the
  submitted set against the stored one. The vitest `include` pattern covers
  `.ts` as well as `.tsx` so these cannot be silently skipped.
- **Advisory-not-blocking assertions.** Where the domain says a rule is
  report-only — modifier satisfiability above all — the test asserts both
  that the warning appears _and_ that the write still succeeds.
- **Error identity, not error presence.** Where a change moves a validation
  error, the test pins the error's type, location, and message rather than
  asserting that the field is mentioned somewhere. The dietary-tag element
  case is the worked example: a loose assertion covered it, passed under both
  the old and the new error, and so concealed the one behaviour the change
  actually moved.

Layout, computed contrast, touch geometry, and focus visibility are
deliberately **not** asserted in jsdom, which computes none of them. They are
verified by driving the real stack in a browser at 320 px, 768 px and 1280 px
against the disposable E2E database (ADR-018). That is engineering evidence
rather than a WCAG certification — no axe-core scan is run — and it is not a
standing per-change requirement. At the time it was also **not committed
tooling**: the driver was assembled per run, so the evidence was reproducible
only by repeating a documented procedure. M3F closes that gap for the
milestone's own acceptance bar by committing phone-width coverage (see the
M3F section above); whether broader visual tooling should follow is still
open.

## Earlier state (Milestone 3D)

The public surface carries permanent contract tests of its own. Three
kinds are worth naming because they exist to protect decisions rather
than behavior:

- **Route invariants.** Every registered `GET`/`HEAD` route under
  `/api/v1/public/` must carry `resolve_public_business` in its effective
  dependency graph — a recursive walk of the FastAPI dependency tree that
  includes schema-hidden `HEAD` companions, with a positive control (the
  route list may not be empty) and a negative control (a route without
  the resolver is detected). The host-guard exemption is only safe
  because of this test, so it fails the suite rather than a review.
- **Non-disclosure by denylist.** Public schemas are checked against a
  denylist of administrative and storage field names rather than an
  allowlist, so the check keeps failing as the contract grows. Response
  bodies, headers, and captured logs are asserted free of storage keys,
  paths, checksums, and filenames on both success and every failure path.
- **Bounded queries.** A one-category menu and a twelve-item,
  three-category menu with modifiers and images must cost exactly the
  same number of statements; an all-hidden menu must cost fewer, proving
  child reads are genuinely skipped rather than fetched and discarded.
  Representative sizes are deliberate — building a policy-maximum fixture
  to prove absence of N+1 would cost runtime without adding evidence.

Concurrency cases force their interleaving by patching a single
repository call to mutate the database just before it reads, which is
deterministic where racing real clients is not. Public media delivery is
covered for eligibility (detached, hidden-only, hidden-category-only,
pending, foreign), conditional requests, header contracts, the stat/open
race, and the discipline that expected public misses emit no warning.

## Earlier state (Milestone 2F)

The end-to-end layer exists (ADR-016): four Playwright journeys —
onboarding (the blueprint's mandatory journey #1: create → honest
missing-owner conflict → owner invitation with one-time token → guest
acceptance → activation), negative authorization, the anonymous
redirect round-trip, and lifecycle-plus-audit — run Chromium-only,
one worker, `fullyParallel: false`, zero retries. Every spec is
order-independent: it owns a fixed namespace (`e2e-onb`, `e2e-authz`,
`e2e-lc`) inside a database recreated fresh each run, creates its own
prerequisites (through the UI when that is the journey, through
authenticated API fixtures otherwise), and filters audit assertions to
its own business. A single Node orchestrator (`pnpm e2e`, docs/05) owns
ports, the disposable `restaurant_engine_e2e` database (exact-allowlist
reset script; the development database is unreachable by construction),
CLI admin seeding, both servers, Playwright, and guaranteed cleanup;
its failure paths are covered by a node:test regression suite with
injected fakes. CI runs the identical entry point in a fifth `e2e` job
and uploads failure-only artifacts with bounded retention. Component
tests (Vitest, injected client) own the platform UI's states and a11y
behavior; Playwright exercises only real cross-stack journeys.

## Earlier state (Milestone 2A)

The security/tenancy layer began with M2A: a permanent `tests/security/`
suite (PostgreSQL-backed, auto-marked `integration`) proves the ADR-010
contracts — uniform login failure compared under an injected fixed
correlation ID, backoff counter semantics, session rotation/revocation/
idle/absolute expiry, cookie flags per environment, the full fail-closed
CSRF precedence matrix, storage and log hygiene (no plaintext tokens or
passwords anywhere), and bootstrap CLI safety. Migration tests now walk
the revision chain **stepwise** (every migration applies against the
previous head) and prove downgrades are real. Audit detail schemas are
denylist-tested so the `details` column can never carry secrets. The
api-client suite covers the auth facade group with an injected fetch.

## Earlier state (Milestone 1C)

The API contract is under permanent test (ADR-009): backend unit tests
prove the canonical OpenAPI export is deterministic, byte-identical to the
committed `packages/api-client/openapi.json`, and carries exactly the
declared, unique operation ids; boot-time validation tests prove a route
without an explicit `operation_id` (or with a duplicate) cannot compose.
`packages/api-client` carries Vitest facade tests with an injected fetch —
typed success payloads, the ADR-008 error envelope on 503, non-JSON bodies,
and network failure — with no network and no running backend. The CI
`contract` job runs the identical local command `pnpm contract:check`
(temp-directory regeneration, byte-compare, repository untouched).
`pnpm smoke:dev` is the documented proof that the one-command dev stack
serves both health probes and both shells; it is deliberately not a CI job
(CI builds and tests every component individually).

## Earlier state (Milestone 1B)

Frontend tests live in each app (`apps/*/tests/`), run with **Vitest +
Testing Library + jsdom** via `pnpm test` from the root:

- **storefront** — placeholder page and not-found page render with the right
  headings/links; layout/page/not-found metadata declare the expected
  document titles (async server-component rendering is deliberately not
  simulated; shell pages are synchronous components).
- **control-center** — the exported route table is exercised through a real
  memory router: `/` renders the layout landmarks and home page with the
  right `document.title`; an unknown path renders the not-found page.

Production builds are part of the gate (`pnpm build`, zero environment
variables). Playwright/e2e remains deferred until the first real journey.

The backend foundation ships with real tests in `backend/tests/`:

- **unit/** — settings validation, error-envelope contract, constraint
  naming convention (no I/O);
- **api/** — health probes, correlation-ID behavior, error handlers, request
  logging, via the FastAPI test client (no database required);
- **integration/** — readiness against real PostgreSQL and
  `alembic upgrade head` from an empty scratch database. These carry the
  `integration` marker (applied automatically by directory) and **fail with
  a clear message — never skip — when the database is down**, so the suite
  cannot go green while silently not testing the database.

Run with `uv run pytest` (see docs/05 for marker selection). CI runs the
identical commands against the same pinned PostgreSQL image. Frontend and
end-to-end layers arrive with their surfaces (M1B onward).

## Test layers

| Layer               | Purpose                              | Examples                                            |
| ------------------- | ------------------------------------ | --------------------------------------------------- |
| Domain unit         | Fast business-rule feedback          | Modifier selection, status transitions, pickup time |
| Service integration | Transaction and persistence behavior | Publish state machine, order snapshot, reorder      |
| API                 | Auth, schemas, errors, permissions   | Login, menu commands, platform suspend              |
| Security/tenancy    | Permanent isolation contracts        | Cross-tenant IDs, uploads, cache, membership        |
| Frontend component  | Important interaction behavior       | Modifier form, publish warning, order ticket        |
| End-to-end          | Critical journeys across deployments | Onboard → publish; order → accept → ready           |
| Operational         | Restore and deployment confidence    | Migration on production-like DB, backup restore     |

## Database policy (ADR-005)

PostgreSQL is used for integration and API tests that depend on constraints,
transactions, JSONB, or locking. SQLite may be used **only** for pure tests
whose behavior is database-independent. A production PostgreSQL system does
not claim confidence from an SQLite-only suite. Tests use isolated databases
or schemas and deterministic factories; migrations are applied in CI rather
than relying on ORM table creation.

## Mandatory end-to-end journeys (by first commercial release)

1. Platform admin onboards a restaurant and owner.
2. Owner logs in, creates a menu, uploads an image, edits content, publishes.
3. Public visitor sees only the published version under the correct host.
4. Visitor customizes an item and places one pickup order despite a
   simulated retry.
5. Staff accepts, prepares, and marks the order ready; visitor sees status.
6. Tenant A cannot discover or modify tenant B data through API or UI.
7. Suspended tenant becomes unavailable publicly without data loss.

## Quality gates

A pull request cannot merge unless the checks relevant to its contents pass.
The full gate (from Milestone 1 onward, growing with the codebase):

- Ruff lint and format check; Python type check at the agreed strictness;
- pytest unit/integration/API/security suites;
- ESLint and Prettier; strict TypeScript; frontend unit tests;
- production builds;
- OpenAPI client regeneration produces no unexplained diff;
- migration upgrade from the previous schema succeeds;
- Playwright smoke suite for protected milestone branches;
- dependency/secret scan.

During Milestone 0 the gate is the subset that applies to existing files:
formatting, linting, configuration consistency, and repository hygiene.

Coverage is a diagnostic, not a target substitute: critical state machines
and tenant boundaries require behavior coverage regardless of the global
percentage.
