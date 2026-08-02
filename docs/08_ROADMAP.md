# 08 — Roadmap

Summarizes blueprint §19 with the approved Milestone 0/1 boundary correction
(2026-07-14). Each milestone must be demoable, testable, documented, and
mergeable. Do not start the next milestone while exit criteria remain open
unless the exception is recorded.

## Milestone boundary decision (2026-07-14)

Principal architecture review resolved a scope conflict between the governing
documents: **Milestone 0 is the architecture and repository contract only**
(governance, handbook, ADRs, hygiene, tooling and workspace contracts, CI
appropriate to existing files). All runnable components — the FastAPI
application, health endpoints, Docker Compose PostgreSQL, frontend shells,
OpenAPI export and generated client, and application tests — belong to
**Milestone 1**. Both governing documents were amended accordingly in the
initial architecture-contract commit.

## Status

| Milestone                                                      | State                                              |
| -------------------------------------------------------------- | -------------------------------------------------- |
| M0 — Architecture and repository contract                      | **Complete** (2026-07-14)                          |
| M1 — Platform foundation                                       | **Complete** (2026-07-15)                          |
| M2 — Identity, tenancy, and onboarding                         | **Complete** (2026-07-19)                          |
| M3 — Catalog and media                                         | **Complete** (2026-07-23)                          |
| M4 — Storefront composition and publication                    | **Complete** (2026-07-30)                          |
| M4G — Curated storefront design and motion (extension)         | **Complete** (2026-08-01; M4G-A–M4G-D, ADR-024)    |
| M5 — Hours and pickup readiness                                | **In progress** (M5A complete 2026-08-01, ADR-025) |
| M6 – M8 — Ordering, operations, pilot                          | Not started                                        |
| M9 – M11 — Commercial growth (promotions, campaigns, Facebook) | Not started (planned; reconciliation 2026-07-23)   |

## Milestone 5 delivery decision (2026-08-01)

The approved M5 architecture (ADR-025, with binding rulings D1–D7)
subdivides M5 into five independently reviewed slices, one PR each. M5B
and M5C depend on M5A; M5D depends on M5A and M5B; M5E depends on all of
them.

| Slice                         | Scope                                                                                                                                                                                                                   | State                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **M5A** — Hours foundation    | `business_hours` / `schedule_exceptions` / `fulfillment_settings` + migration, pure DST-safe timekeeping/availability core, admin API, platform timezone command (D2), capability, audit actions, contract regeneration | **Complete** (2026-08-01, ADR-025) |
| **M5B** — Public availability | `GET /api/v1/public/availability`, neutral failure semantics, `no-store` (D4), isolation tests                                                                                                                          | **Complete** (2026-08-02, ADR-025) |
| **M5C** — Hours workspace UI  | `/businesses/:id/hours`: weekly editor with DST-gap warning, exceptions, fulfillment settings                                                                                                                           | Not started                        |
| **M5D** — Storefront display  | `hours` section + three renderer arms + composer control (one slice), JSON-LD hours, request-cost assertion update                                                                                                      | Not started                        |
| **M5E** — E2E and close-out   | journeys, per-variant acceptance for the new section, documentation, exit-criteria verification                                                                                                                         | Not started                        |

### M5B close-out (2026-08-02)

M5B delivered the **public availability projection** —
`GET /api/v1/public/availability` (`public_availability_get`, plus a
schema-hidden `HEAD` companion), host-resolved through the established
resolver so only the Host selects a Business, only an **active**
Business answers, and unknown, provisioning, suspended, closed,
reserved, and malformed hosts are one indistinguishable neutral 404.
Every active business answers: no configured hours is honestly closed
(`is_open_now: false`, empty weekly, nothing upcoming), because an
empty schedule is a real operational state the storefront must render.
The projection derives entirely from structured settings through the
pure core — the weekly schedule and upcoming exceptions in the D1
minute encoding plus the tenant timezone, and the instant facts
(`is_open_now`, `closes_at`, `next_opens_at`, `next_pickup_at`) as UTC
instants. Exceptions are listed for a bounded 60-day forward window;
pickup facts are deliberately minimal (`enabled`, `asap_enabled`,
`next_pickup_at`) until M6 needs more. **No cache grant was added
(ruling D4)**: the global `no-store` default applies to successes and
errors alike, pinned by test on both paths. Contract **73 → 74**; the
public client facade gains `getAvailability()`; `effective_policy()` is
shared by the member preview and this projection so both derive from
one fallback.

**Verification.** Backend **1,240** (from 1,228; twelve new public
contract tests — the neutral-404 matrix, the honest-empty projection,
exception precedence with the D6 note, pickup facts, the bounded
window, `no-store` on success and failure, the HEAD companion,
cross-host isolation, and suspension-preserves-rows — all time-robust
by construction); api-client **109** (from 106); every other suite,
budget, and build gate unchanged and green; the public-surface
invariant test covers the new route automatically.

Merge evidence (PR #43):

- Reviewed feature head `2bcd0899dcf3b9b1575a970b9c310191c0e8ba66`,
  merged to `main` as `b9e21c66a7cd6cecbf9555e53d5a050048f12cca`
  (ordered parents `02f59e5651b52a3bd19ad887bd94fb3f0aa8d689` then the
  reviewed head; the merge tree equals the reviewed feature-head tree).
- Exact-head PR CI run `30732083089` completed successfully — five
  jobs green, zero artifacts, attempt 1.

**The failed merge run, recorded plainly.** Exact-merge push CI run
`30732209402` **failed twice** — attempts 1 and 2 — in the e2e job, in
the pre-existing storefront-design-assignment isolation journey
(untouched by M5B): the first anonymous SSR render after a quiet gap in
storefront-to-backend traffic got a connection-level fetch failure (no
request reached the backend; requests 40 ms either side returned 200),
the page honestly rendered its 500 boundary, and the 200 assertion
failed; 22 of 23 tests passed on both attempts. The identical tree had
passed the complete suite on the exact-head run and twice locally the
same day, on the same runner image (ubuntu-24.04 `20260720.247.2`) and
Node (24.18.0), excluding environment drift. The best-supported cause —
stated as such, not proven — is uvicorn's default 5-second keep-alive
idle timeout sitting barely above undici's ~4-second idle-socket reuse
window, a race that CI load can close. Corrective PR #44 (the M4G-C
pattern) added `--timeout-keep-alive 75` to the **orchestrated E2E
backend only** — no assertion weakened, no retry added, no production
runtime change (production keep-alive is a deployment concern behind
nginx, M8). Its exact-head run `30732731236` and the exact-merge push
run `30732874509` on merge `4836e6939d2cc2d5e6190e0f296ff6ba77d8c795`
(parents `b9e21c66` then reviewed head `03e8bdf9`, tree equal) both
completed successfully with five green jobs, zero artifacts, attempt 1
— `main` is green again. **A fourth retained risk is recorded:** if
this failure signature ever reappears with the flag in place, the
keep-alive reading is falsified and the investigation must reopen
rather than escalate the tolerance.

**Boundary.** No UI (M5C), no `hours` storefront section or renderer
change (M5D), no browser-level hours coverage (M5E), no ordering
behavior (M6). M5C and M5D each need their own review.

### M5A close-out (2026-08-01)

M5A delivered the **hours domain foundation** — the first Milestone 5
slice and the first schema change since M4A. Three additive tenant-owned
tables land on one migration (`c3d8f5a21e47`, from `a41d9c7e5b30`):
`business_hours`, `schedule_exceptions`, and `fulfillment_settings`,
with the D1 minute encoding (`closes_minute` above 1440 ends the
interval on the following local day), CHECK-bounded values everywhere, a
partial unique index allowing at most one closed-all-day exception row
per date, and a per-business fulfillment singleton whose **absence
projects the documented defaults** and materializes only on first write
(the M4G-A mechanism — no backfill, existing tenants gain no rows).

**The pure core is the milestone's substance.** `hours.timekeeping` and
`hours.availability` take `now` as an argument and touch neither the
database nor the ambient clock, so the DST exit criteria are met
deterministically at the unit layer: spring-forward gap boundaries move
forward to the gap's end (proven for every minute of the New York gap);
fall-back openings take the earlier occurrence and closings the later,
so the open window is the union; overnight intervals convert end-to-end
and one entirely inside a gap contributes nothing; exceptions replace
their date's weekly schedule while an overnight interval still belongs
to the service day that opened it; the next-opening scan is bounded so
a business with no hours terminates. The matrix covers America/New_York,
America/Phoenix (no DST), Australia/Sydney (southern hemisphere), and
Australia/Lord_Howe (a thirty-minute shift), plus year-boundary and
multi-day-closure searches and the pickup-slot rules (real-time
stepping, lead time, cut-off, service-day horizon).

**The API surface.** Six business-scoped operations (the established
capability → Business `FOR UPDATE` → lifecycle preamble; closed
businesses readable, mutations 409 `invalid_state`; both write commands
exact full-set replacements with the exact no-op suppressed) plus the
platform timezone correction (ruling D2, audited with both values — the
first repair path for a creation-time tenancy fact). Contract **66 →
73** operations, regenerated through the pinned generator; the client
gains the `hours` facade group and `platform.setTimezone`. Reads ride on
`business.view` (ruling D7 — staff see the schedule they work); writes
require the new `business.hours.write` (owner/manager). Five audit
actions ship with typed detail schemas and read-time projections; the
D6 exception note's content never enters an audit payload.

**Verification.** Backend **1,228** (from 1,132; the migration walker
covers the new revision stepwise including downgrade); api-client
**106** (from 95); storefront-renderer 146, storefront 70,
control-center 439, Playwright 23, and the E2E orchestrator unchanged.
Ruff lint/format clean, mypy strict clean (193 files), workspace
lint/format/typecheck clean, `contract:check` byte-current, both
production builds green, first-load JS 456,547 B against the unchanged
502,201 B ceiling, built-server verification green, and `pnpm e2e` 23
passed with full disposable cleanup. Only the disposable test databases
were touched; dev and UAT databases and media roots are untouched.

Merge evidence (PR #41):

- Reviewed feature head `dc156ed173510f17c3cbc0bc705c0c0bb1cf2a0e`,
  merged to `main` as `0f46640a7548402a878bc7c2e4da134906740971`
  (ordered parents `37ff016f455f4881d8342cb1d7ef22f2259b3dcf` then the
  reviewed head; the merge tree `80f6e39c` equals the reviewed
  feature-head tree).
- Exact-head PR CI run `30730811615` and exact-merge-SHA push CI run
  `30730938069` both completed successfully — all five jobs
  (repository-contract, backend, frontend, contract, e2e) green, zero
  artifacts, attempt 1.

**Boundary.** No public availability endpoint (M5B), no UI (M5C), no
`hours` storefront section or renderer change (M5D), no browser-level
coverage of hours (M5E), and no order throttling (ruling D3 — it cannot
be enforced before orders exist; M6 owns it). The pickup-slot service
deliberately has **no consumer until M6**: it is proven by its unit
suite and the member preview probe, not by a checkout. M5B–M5E each need
their own review.

## Milestone 3 delivery decision (2026-07-19)

The approved M3 architecture (proposal + addendum + binding rulings,
ADR-017) subdivides M3 into six independently reviewed sub-milestones, one
PR each: M3B depends on M3A; M3C depends on M3A; M3D depends on M3A–M3C;
M3E depends on the stable M3A–M3C administrative contracts (and any M3D
behavior it directly consumes); M3F depends on all earlier slices.

M3E covers the control-center business workspace and menu administration UI
(ADR-018) and is delivered. Its architecture was approved on 2026-07-22,
**after** the implementation already existed — an inversion of the intended
sequence that ADR-018's process record documents in full, and that the
milestone's acceptance does not erase. Two rounds of review corrections and a
business-boundary defect found in final review were resolved before merge.

The Playwright menu journey remains **deferred to M3F** — M3E's automated
coverage is component/integration level, and its visual acceptance is a
disposable-environment check, not new end-to-end specs.

| Sub                              | Scope                                                                                                                                                                                      | State                                      |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------ |
| **M3A** — Catalog core backend   | menu categories/items, dietary tags, integer minor-unit pricing, availability/hidden/featured, transactional normalized reorder, catalog capabilities, admin APIs, audit, isolation matrix | **Complete** (2026-07-20, ADR-017)         |
| **M3B** — Modifiers backend      | modifier groups/options, selection rules, satisfiability model, admin APIs                                                                                                                 | **Complete** (2026-07-20, ADR-017)         |
| **M3C** — Media backend          | media domain, storage adapter, upload pipeline, responsive WebP variants, pending/active lifecycle, sweep, item image attachment                                                           | **Complete** (2026-07-21, ADR-017)         |
| **M3D** — Public menu API        | host-resolved public menu + public media delivery, neutral-404 contract                                                                                                                    | **Complete** (2026-07-21, ADR-017)         |
| **M3E** — Menu administration UI | business workspace + menu management in the control center                                                                                                                                 | **Complete** (2026-07-22, ADR-018)         |
| **M3F** — E2E and close-out      | Playwright menu journey, verification, final documentation                                                                                                                                 | **Complete** (2026-07-23, ADR-019, PR #17) |

## Milestone 3 close-out (2026-07-23)

Milestone 3 is **complete**. Owner UAT was accepted on 2026-07-23 — the
corrected invitation-acceptance flow, restaurant activation, owner access, the
menu-management corrections, the responsive/mobile review, and creation and
activation of an additional restaurant. M3F (the Playwright menu journey,
verification, and this close-out) is delivered, completing the M3A—M3F
progression.

Merge evidence (PR #17):

- Reviewed feature head `47276f4bb3be9c121015de0f9d52f93be335aedb`, merged to
  `main` as `742659122c008ed93c6eeea428f4c26e3f935c60` (ordered parents
  `caafc1bdcdc7d74a409f47be43e793d2563fecaf` then
  `47276f4bb3be9c121015de0f9d52f93be335aedb`; the merge tree equals the
  reviewed feature-head tree).
- Branch CI run `30060951076` and post-merge push CI run `30061694722` both
  completed successfully — all five jobs (repository-contract, backend,
  frontend, contract, e2e) green, zero artifacts.
- PR #17 also carried the owner-UAT menu/interface corrections and the
  commercial roadmap reconciliation.

M4 had not started at this close-out. The future commitments recorded by the
reconciliation (customer ordering and order management, promotions and
checkout-integrated discounts, pop-up campaigns, Facebook Page publishing,
the expanded Control Center, and later
notifications/payments/delivery/POS/reporting) remain future work in
milestones M4—M11 and are not implemented by this close-out.

## Milestone 4 delivery decision (2026-07-26)

The approved M4 architecture (ADR-020, with binding rulings D1–D9)
subdivides M4 into six independently reviewed sub-milestones, one PR each.
M4A–M4C are strictly sequential; M4D and M4E may proceed in parallel once
M4C lands; M4F depends on all of them.

| Sub                                     | Scope                                                                                                                                                                                  | State                              |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **M4A** — Storefront foundation         | storefront domain, section registry, design-variant registry, composition contract, `storefront_versions` persistence, migration                                                       | **Complete** (2026-07-26, ADR-020) |
| **M4B** — Administrative API            | draft read/update, publication, restore, platform design assignment, capabilities, audit actions, media claiming                                                                       | **Complete** (2026-07-28, ADR-020) |
| **M4C** — Public projection and caching | public storefront endpoint, media predicate extension, bounded business-keyed caching                                                                                                  | **Complete** (2026-07-29, ADR-020) |
| **M4D** — Server-rendered storefront    | `apps/storefront` rendering, section renderers, SEO basics, performance/accessibility budgets, Unicode/complex-script rendering verification (Bengali as the required initial fixture) | **Complete** (2026-07-29, ADR-021) |
| **M4E** — Control-center workspace      | storefront workspace: edit, reorder, preview, publish, history, restore                                                                                                                | **Complete** (2026-07-30, ADR-022) |
| **M4F** — E2E and close-out             | mandatory journeys 2 and 3, verification, final documentation                                                                                                                          | **Complete** (2026-07-30, ADR-023) |

M4A delivered the foundation only: registries, the composition contract,
and one additive table. M4B delivered the administrative API over it —
the seven-operation contract (57 → 64), the three storefront
capabilities, publication/restore/history, platform design assignment,
media claiming, and the three audit actions — with **no** migration, no
preview (assigned to M4C with the projection assembler it shares), no
public projection, no caching, and no UI. M4C delivered the public read
path — the host-resolved public storefront projection of the current
published version with its schema-hidden `HEAD` companion, the
authenticated draft preview (contract 64 → 66), the §10 media
delivery-predicate extension, and bounded route-identity caching
(`public, max-age=60` on successful public responses only) — computed
per request, with no renderer, no SEO, no migration, no new dependency,
and no UI. M4D delivered the server-rendered storefront (ADR-021, PR
#25): dynamic Host-resolved server rendering of the published storefront
at `/` and the complete public menu at `/menu`, both gated on the
currently published version; five exhaustive section renderers under the
sole `classic` design variant; the tenant-safe server transport and
development-only media forwarding; neutral lifecycle and error behavior;
published-data-only SEO with canonical origins, per-host robots and
sitemap, and the audited Restaurant JSON-LD boundary; responsive
projection-supplied media and the accessibility floors; English-first
universal U.S. positioning with Bengali used only as the required
Unicode/complex-script engineering fixture; and the enforced
performance budget with built-server verification — with no backend,
contract, migration, or external-dependency change. M4E delivered the
control-center storefront workspace (ADR-022, PR #27): four
deep-linkable workspace pages (overview/composer, saved-draft preview,
history, version detail) over the shipped seven-operation contract;
full-document explicit draft saving with exact create/update intent and
an explicit stale-conflict state; composition of all five registered
section types with keyboard-first ordering, staged hero/gallery media
claimed at save, and the accent token; owner-only publication and
archived-only restore behind deliberate confirmations; the
lifecycle-aware owner/manager/staff permission matrix with honest
denial and closed-business read-only presentation; and the
framework-neutral shared renderer (`packages/storefront-renderer`)
consumed by both applications, keeping public links active while
preview navigation is structurally inert — with no backend, schema,
OpenAPI, or generated-client change and the public rendering proven
pixel-identical to the M4D baseline. M4F delivered the end-to-end
verification close-out (ADR-023, PR #29): the E2E orchestrator now
starts the storefront dev server as its third tracked child (backend →
storefront → control center), the mandatory journeys 2 and 3 are
complete for the first time — one cohesive browser journey covering
composition of all five section types, saved-draft preview, publication,
the cross-host published-versus-draft contract, archived-only
restoration (which structurally requires a second publication), and
suspension/reactivation of the same published output — plus responsive
acceptance for the `classic` storefront across six viewports on both
public routes and blocking browser accessibility verification (zero axe
violations across eight page/states within the WCAG 2.0/2.1 A/AA rule
boundary, with no exclusions; engineering evidence, not WCAG
certification). M4F changed no production runtime or CI workflow file
and added one development-only dependency (`@axe-core/playwright`,
exact-pinned). **With M4F delivered, Milestone 4 is complete** — see the
close-out section below.

## Milestone 4 close-out (2026-07-30)

Milestone 4 is **complete**. M4F (the end-to-end storefront journeys,
responsive and accessibility verification, and this close-out) is
delivered, completing the M4A—M4F progression. The blueprint §19 exit
criteria are verified: invalid configurations cannot save (backend
validation and workspace 422-mapping suites), a published configuration
always renders (renderer exhaustiveness and fail-closed suites, the
built-server verification, and the rendered public journey), a draft is
never public (projection/preview suites plus the journey's
pre-publication, post-edit, and post-restore public assertions), and the
performance/accessibility budgets pass (the enforced first-load
JavaScript budget, the built-server checks, the six-viewport responsive
matrix, and the zero-violation accessibility boundary — engineering
evidence, not a WCAG certification).

Merge evidence (PR #29):

- Reviewed feature head `11b884485209ce7e5675efc670767fe5b099cde3`,
  merged to `main` as `09bccffae59191118c5432a9e788ec30297efcf5`
  (ordered parents `9f74071b285da299cee298a5a957bd2775b18997` then
  `11b884485209ce7e5675efc670767fe5b099cde3`; the merge tree equals the
  reviewed feature-head tree).
- Exact-head PR CI run `30577609020` and exact-merge-SHA push CI run
  `30578356793` both completed successfully — all five jobs
  (repository-contract, backend, frontend, contract, e2e) green, zero
  artifacts; the e2e job ran the full thirteen-test browser suite on
  Linux through the three-server orchestration with proven cleanup.

M4G (curated storefront design and motion) is recorded in ADR-023 as
the proposed next slice before M5; it requires its own roadmap
reconciliation, discovery, and authorization and is **not** part of this
completed milestone. M5 has not begun.

## M4G reconciliation (2026-07-30)

Documentation-only reconciliation performed after the Milestone 4
close-out (the reconciliation ADR-023 §7 required). It **adds no
application code, API, schema, migration, or dependency**, and it does
not reopen Milestone 4, which remains historically complete above.

**M4G — Curated Storefront Design and Motion** is the separately
authorized post-close-out extension scheduled **before Milestone 5**.
Its approved architecture is
`docs/decisions/ADR-024-curated-storefront-design-and-motion.md`; the
rulings there are binding. In summary:

- **Three production-ready curated variants** — the existing `classic`
  plus `editorial` (premium typography, larger imagery, spacious,
  strongest scroll-linked storytelling) and `express` (compact,
  menu-and-action-oriented, minimal motion) — as renderer layout arms
  behind the existing exhaustive dispatch, with section renderers
  shared and never forked per variant.
- **A curated brand surface** owners select within platform-authored
  registries: five accessible palettes (AA-verified at build time),
  three system-font typography pairings (no webfonts; complex-script
  fallbacks preserved), and an optional tenant logo staged and claimed
  like section media. All of it lives in the versioned configuration
  (`schema_version` deliberately stays 1 — additive fields with
  defaults), so snapshots, history, and restore preserve the visual
  configuration; existing tenants render unchanged by default.
- **Motion is pure CSS** (scroll-driven animations under `@supports`):
  zero client JavaScript, budgets and the `'use client'` allowlists
  untouched, the delivered reduced-motion floor applies, and the
  unenhanced static presentation is always complete. The optional hero
  loop is **not** in M4G (media pipeline is image-only; it remains a
  recorded future candidate).
- **The first platform design-assignment UI** (the M4B API exists
  without a UI) lands with the workspace's palette/pairing/logo
  controls.
- **Delivery in four separately authorized slices** — M4G-A backend
  registries/theme/§10-logo extension; M4G-B renderer variants and
  motion; M4G-C control-center and platform UI; M4G-D per-variant
  E2E/responsive/accessibility acceptance and close-out — each with
  the standing verification gates and its own review.

Explicitly outside M4G (ADR-024 non-goals): tenant CSS/HTML/JS, page
builders, theme marketplaces, per-tenant deployments or forks,
webfonts, video or any customer video pipeline, the hero loop,
client-JS animation, and all Milestone 5 behavior. **Milestone 5
remains unstarted** and follows M4G.

Authority: blueprint §19 is unchanged; like the M9–M11 commercial
reconciliation, this section is the reconciliation of record until a
future blueprint review folds it in. No completed milestone record or
historical wording elsewhere in this file was altered.

## M4G delivery decision and slice status

Each ADR-024 §12 slice is separately authorized and reviewed, one PR
each. M4G-B depends on M4G-A; M4G-C depends on M4G-A (its parts that
consume the new variants land after M4G-B); M4G-D depends on all of
them. M4G is an extension **after** the completed Milestone 4;
delivering a slice of it neither reopens Milestone 4 nor starts
Milestone 5.

| Sub                                      | Scope                                                                                                                                                                | State                              |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **M4G-A** — Backend theme foundation     | palette and typography registries, additive `Theme` extension, document-level media collection, §10 theme-logo authorization, contract regeneration                  | **Complete** (2026-07-31, ADR-024) |
| **M4G-B** — Renderer variants and motion | `editorial` and `express` layout arms, palette/pairing token application, `--accent-text`, logo chrome, CSS scroll-driven motion, per-variant CSS-weight measurement | **Complete** (2026-07-31, ADR-024) |
| **M4G-C** — Control center and platform  | composer palette/pairing pickers, logo staging, preview parity, the first platform design-assignment UI                                                              | **Complete** (2026-07-31, ADR-024) |
| **M4G-D** — E2E and close-out            | one journey per variant, per-variant responsive/accessibility/reduced-motion acceptance, visual acceptance, close-out                                                | **Complete** (2026-08-01, ADR-024) |

### M4G-D close-out (2026-08-01)

**M4G is complete.** M4G-D delivered the last ADR-024 §12 slice — the
per-variant browser and visual acceptance suite, plus this close-out —
so all four slices are delivered, each through its own reviewed PR with
green exact-head and exact-merge CI. The extension neither reopened the
historically complete Milestone 4 nor started Milestone 5.

**What M4G-D added.** A test-only change: nine files under `e2e/`
(+1,904/−140), growing `pnpm e2e` from thirteen to **twenty-three**
Playwright tests. A design-assignment fixture drives the real platform
command through an authenticated administrator session; the seeding
fixture gains curated palette, typography, accent, and staged-logo
selections (callers that pass none submit exactly the document they
always did); and a hygiene watcher fails a test on console errors,
uncaught page errors, transport failures, or unexpected 4xx/5xx. Four
specs cover the ADR-024 §11 bars per variant: one representative
journey each for classic, editorial, and express (assignment → saved
draft → preview parity → publication → anonymous tenant-host
rendering); blocking zero-violation axe on published `/` and `/menu`;
the six-viewport responsive matrix for the two new variants through the
same geometric floors as the delivered classic matrix; real-browser
reduced motion (durations collapsed, scroll timelines detached, content
fully visible); the measured 44 px target and painted focus-indicator
floors; the single-`h1` and decorative-logo rules; a pairwise palette ×
typography selection covering all five palettes and all three pairings
in five combinations, including both logo-absence branches; and
assignment-versus-publication, non-administrator denial with the
command proved never called, and cross-tenant isolation with differing
variants.

**Verification.** Locally all gates passed on first attempt (focused
specs 10, complete suite 23, typecheck, formatting, lint, orchestrator
regression 42 with the one known Windows-symlink skip), and visual
acceptance reviewed twenty-eight distinct per-variant captures as
disposable per-run evidence — no committed baselines, no pixel gates
(ADR-023). Implementation PR #39, reviewed head `0baeb35f`, merged
SHA-bound as `300a548832a0ee8026c00b7eb71b248dd1eed581` with ordered
parents `613287c0` then the reviewed head and the merge tree equal to
the reviewed head tree. Exact-head PR CI run `30698457002` and
exact-merge push CI run `30698873815` both completed successfully with
all five jobs green and zero artifacts on attempt 1; the merge run
executed the full twenty-three-test browser suite on Linux (backend
1,132; orchestrator 43; api-client 95; storefront-renderer 146;
storefront 70; control-center 439; first-load JavaScript 456,629 bytes
against the unchanged 502,201-byte ceiling; delivered CSS 10,493 bytes
per route).

**Retained risks, none benign.** (1) The dirty-navigation failure from
run `30652179044` attempt 1 remains unexplained; ADR-024 assigns it no
browser coverage, so M4G-D deliberately added none. (2) The earlier
local E2E non-zero exit remains unidentified; later clean runs do not
explain it. (3) The accent-sweep 15-second allowance remains
unexercised — successful runs since establish nothing about proximity
to it.

**Boundary.** Owner-facing UAT of the M4G surface has not been
conducted. Milestone 5 remains unstarted and follows M4G. No
hero-video pipeline, ordering, checkout, campaign, CRM, or
Facebook-publishing work began.

### M4G-C close-out (2026-07-31)

M4G-C delivered the **control-center and platform** slice over the M4G-A
theme foundation and the M4G-B renderer. It is the first slice that lets
a human choose any of it.

**Governance, unchanged and now visible.** Platform administrators remain
the only actors who assign a structural design variant; the M4B command
is still the sole write path, and M4G-C simply gives it the UI it never
had. Owners see the assigned variant as read-only information in their
workspace and never submit one. Owners **and managers** may edit the
palette, the typography pairing, the accent, and the logo, because those
are tenant content rather than structure. Publication and restoration
remain owner-only, and staff hold no storefront capability at all.

**Brand editing inside the delivered save path.** The composer gained a
"Brand and appearance" group holding the palette picker, the typography
picker, the accent control moved in unchanged, and the optional logo. All
four travel through the existing full-document draft save — no autosave,
no second write path — so they are versioned, published, archived,
restored, and snapshot-preserved by machinery that already existed. The
loaded draft's whole theme is still carried through an edit, so a theme
field this form does not own survives an unrelated change, and a
configuration stored before M4G still reads as the registry defaults.
Both pickers are populated from the renderer's own registries and every
swatch and type sample is painted from its exported tokens, so no palette
colour and no font stack is restated in the control center; a build-time
pin ties the offered sets to the published contract enums.

**Logo staging.** Choosing a logo stages an existing or newly uploaded
media reference in the editor; the draft save performs the existing claim
operation; and only publication can make the asset publicly deliverable.
The placement is permanently decorative — the shared media dialog runs in
a mode that offers no describe/decorative choice and no description
field, and no alt text is stored — because the business name is always
present as text beside it. Every other consumer of that dialog keeps the
description step unchanged, pinned by a regression test.

**Preview.** Preview remains the server projection of the **saved** draft
rendered through the shared renderer, now proved to carry the palette,
pairing, accent, logo, content, and platform-assigned structural variant
faithfully. **No unsaved live preview was introduced**: a picker changes
the storefront only after Save draft, and the page still says so.

**Platform assignment.** The new Design section on the platform business
detail page offers the three variants with **nothing preselected** and
**does not display a current value**, because the platform business
representation does not carry the variant and a platform administrator
holds no storefront read — the panel says plainly where the current
design _is_ visible instead of fabricating one. Its acknowledgements
distinguish the three real outcomes: a first draft created, an actual
variant change, and the command's exact same-variant no-op, which is
never described as a change.

**Error routing.** A stale-write conflict and an expired staged-media
`409 invalid_state` are now distinct: only the backend's own conflict
code enters the stale-draft state, so an expired logo no longer claims
the draft changed elsewhere and the editor stays usable for a retry.
Exactly addressed theme field errors reach the control that owns them,
while the service-level media rejection stays in the form summary,
because that response is indistinguishable by design.

**Verification.** Backend **1,132**; api-client **95**;
storefront-renderer **146**; storefront **70**; control-center **439**
(from 398); E2E orchestrator **43** tests with 0 failed and one
Windows-symlink skip; Playwright **13**, unchanged. Production builds,
built-server verification, contract and generated-client byte-currency,
budgets, lint, formatting, strict typing, and the repository-contract
checks all passed. **No backend, endpoint, generated contract, schema,
migration, dependency, lockfile, publication, restoration, authorization,
tenancy, lifecycle, session, CSRF, renderer-production, or CI-workflow
behavior changed in M4G-C**; every changed path was under
`apps/control-center`.

**Delivery evidence, including the failed first merge run.**
Implementation PR #36; reviewed head
`4ab5b9dc569b386f9085ca67fb1c717e204e19f0`; merged to `main` as
`549b3b55acd89ae6f84652e0d7a61e1cb301ab49`. Exact-head PR CI run
`30671382912` succeeded with all five jobs green and zero artifacts. The
first exact-merge-SHA run `30671894681` **failed**, and only because a
pre-existing M4G-B test — the exhaustive 140,608-point `midnight` accent
sweep, untouched by M4G-C and byte-identical across both runs — exceeded
Vitest's default 5,000 ms per-test limit. It was a timeout, not an
assertion failure. Corrective PR #37 changed exactly one test's local
timeout and nothing else; its exact-head run `30673935509` succeeded, it
merged as `49aa17e89b51b99a1fb72f9fc9ea04daadd3f52c`, and the final
exact-merge run `30674669713` succeeded. Both successful corrective runs
had five green jobs and zero artifacts, and **neither exercised the
15-second allowance** — the sweep finished under the old limit on those
runners.

**Retained risks, none benign.** (1) Attempt 1 of run `30652179044`
failed in the dirty-navigation test in
`apps/control-center/tests/storefront-dialogs-a11y.test.tsx`; its cause
remains unproven and M4G-C did not modify that test. (2) An earlier local
E2E invocation reported passed tests but returned a non-zero exit; its
cause remains unidentified. (3) The accent-sweep timeout correction
passed both required CI gates, but because neither successful run
exercised the new allowance, **runner variability and latent
nondeterminism are not excluded**.

**Boundary.** M4G-D owns the complete per-variant browser-acceptance
matrix — real-browser journeys, responsive viewports, axe, reduced
motion, target geometry — plus visual acceptance and the M4G overall
close-out. No hero-video pipeline, ordering, checkout, campaign, CRM,
Facebook-publishing, or UAT work began. **M4G remains in progress**,
Milestone 4 remains historically complete and is not reopened, and
Milestone 5 remains unstarted.

### M4G-B close-out (2026-07-31)

M4G-B delivered the **renderer** slice: the three curated variants and
their motion, over the M4G-A theme foundation. `DesignVariant` gained
`editorial` and `express` in the same change that shipped their layout
arms, so the enum and the renderer cannot drift apart; `classic` remains
the platform default and the exhaustive dispatch still ends in
`assertNever`. **Section renderers stay shared** — one component per
section type, no per-variant fork — and each variant expresses itself
only through its own chrome, the tokens its root sets, and CSS scoped
under that root.

The five curated palettes (`warm`, `ember`, `slate`, `olive`,
`midnight`) and three system-font pairings (`humanist`, `serif_display`,
`geometric`) reach the page as one typed custom-property set applied at
the `.tenantPage` boundary — the public `<body>` and the control-center
preview container — so the painted browser canvas and every descendant
read the same source. `warm` and `humanist` reproduce the delivered
presentation, so an untouched configuration renders as it did before.
The one derived token, `--accent-text`, is computed at render time from
the stored accent and that version's palette and is **never persisted**:
the stored tenant accent is not rewritten, and an accent that already
clears the contrast floor is returned unchanged.

The optional tenant logo renders through one shared component with a
literal `alt=""` that is never omitted, beside the business name, which
remains the visible semantic `h1` in every variant; a missing or failed
logo falls back to name-only chrome. Motion is pure CSS scroll-driven
animation inside `@supports` guards, authored so the unenhanced state is
the complete, fully visible presentation; the delivered reduced-motion
floor is preserved and strengthened, and no motion touches purchasable
menu content. **Zero client JavaScript** was added: both
client-component allowlists are unchanged, and the first-load JavaScript
budget is unmoved.

The contract widened **only** the `DesignVariant` enum — 66 operations,
`paths` and the operation mapping byte-identical, no schema added or
removed. `schema_version` stays 1, the Alembic head stays
`a41d9c7e5b30`, and there is no migration, endpoint, dependency,
webfont, animation library, or lockfile change.

**Verification.** Backend **1,132**; api-client **95**;
storefront-renderer **146**; storefront **70**; control-center **398**;
E2E orchestrator **42** passed with one Windows-symlink skip; Playwright
**13**; the new CSS-measurement regression suite **13**. Production
builds, built-server verification, contract and generated-client
byte-currency, budgets, lint, formatting, strict typing, and the
repository-contract checks all passed. First-load JavaScript measured
**456,547 bytes** for `/` and for `/menu` against the unchanged
**502,201-byte** ceiling. Delivered CSS measured **10,493 bytes per
route** for Classic, Editorial, and Express alike; authored per-variant
stylesheets measured Classic **2,369**, Editorial **4,206**, Express
**2,200** bytes, reported as diagnostic only. The equal delivered totals
are the measured consequence of the static exhaustive registry importing
every layout arm — **no CSS threshold was introduced** (ADR-024 §11).

**Delivery evidence.** Implementation PR #34; reviewed head
`b026054bd8dd89d6892eed135040b468c82f61ba`; merged to `main` as
`f0f30d6b2c5ea2d7eaf99594db300b21dc22e513` with ordered parents
`17338e80d71d01e6e5d83ecdd39f79e93311c5de` then
`b026054bd8dd89d6892eed135040b468c82f61ba`, the merge tree
`2b1c6ca8dbb0a8c173b9ca2d28364a2e9a9e7244` equal to the reviewed
feature-head tree. Exact-head PR CI run `30649288931` and
exact-merge-SHA push CI run `30649849039` both completed successfully
with all five jobs green and zero artifacts.

**Boundary.** M4G-B shipped no control-center behavior: no composer
palette or pairing picker, no logo upload or staging workflow, and no
platform design-assignment UI — all M4G-C. The complete per-variant
browser-acceptance matrix (responsive, axe, real-browser reduced motion,
visual acceptance) and the M4G overall close-out remain M4G-D. No video
or hero-loop pipeline exists. **M4G remains in progress**, Milestone 4
remains historically complete and is not reopened, and Milestone 5 has
not begun.

### M4G-A close-out (2026-07-31)

M4G-A delivered the **backend foundation only**. Two permanent
server-owned registries ship beside the platform-assigned design-variant
registry — `PaletteId` (`warm`, `ember`, `slate`, `olive`, `midnight`)
and `TypePairingId` (`humanist`, `serif_display`, `geometric`) — each an
append-only `StrEnum` with an explicit named default, published in the
OpenAPI document as a closed enum. They live in their own module because
the governance split is the product: the structural variant is
platform-assigned, while palette, pairing, and logo are tenant content.

The composition `Theme` gains `palette`, `type_pairing`, and an optional
decorative `logo` (`media_id` only — the logo is permanently decorative,
so no alt text exists to store), all with defaults that reproduce the
delivered presentation. **`schema_version` deliberately remains 1**: a
configuration written before M4G reads as `warm` / `humanist` / no logo,
so legacy accent-only configurations stay readable and unchanged. Reads
project those defaults without rewriting stored JSON or advancing
`lock_version`.

Media references are now collected at **document level**, so the theme
logo travels the existing validate-all-before-claim path exactly as a
section image does; the completeness invariant was raised to the whole
canonical document, so no future image-bearing field can escape the
claim path. The public projection reads the immutable published snapshot,
so a published or archived version projects the theme it was published
with. The ADR-020 §10 predicate gained an **independent third leg**: a
published version's `theme` authorizes its logo regardless of section
enablement, while draft-only, archived-or-superseded-only,
disabled-section-only, removed, and cross-business references still
authorize nothing. Corrupt or unregistered stored theme values fail
closed through the established boundaries — the neutral 404 on the
anonymous media route, the opaque 500 on the projection. In the control
center, an unrelated accent edit now preserves the complete loaded theme,
including any field a future contract adds.

The OpenAPI document and generated TypeScript client were regenerated
through the pinned generator; the **operation count stays 66** with no
renamed operation id and the `paths` object unchanged. The **Alembic head
stays `a41d9c7e5b30`** — no migration, no backfill, and no new column.

Deliberately **not** in M4G-A: no renderer theme styling and no public
visual change (existing storefronts render exactly as before); no theme
picker or owner adoption workflow; no logo upload or staging workflow; no
new endpoint; no new database column or Alembic revision; no dependency
or lockfile change; and no M4G-B, M4G-C, M4G-D, or Milestone 5 behavior.

Merge evidence (PR #32):

- Implementation commit `7b7e5ed6e46e0cede5f60e4ac463a4fda5c7bc0f`,
  merged to `main` as `4b695077c8d2874ab7026352b39a67585aaee9c2`
  (ordered parents `04bc09861dfcfb9c8d3a3327714763dda7c6d6bd` then
  `7b7e5ed6e46e0cede5f60e4ac463a4fda5c7bc0f`; the merge tree equals the
  reviewed feature-head tree).
- Exact-head PR CI run `30601961380` and exact-merge-SHA push CI run
  `30602476429` both completed successfully — all five jobs
  (repository-contract, backend, frontend, contract, e2e) green, **zero
  artifacts**.
- Verified counts: backend **1132**, api-client **95**,
  storefront-renderer **52**, storefront **66**, control-center **398**,
  Playwright **13**. Ruff lint and format checks green; strict mypy clean
  across **181** source files; the generated-contract drift check
  byte-current at 66 operations; workspace typecheck, lint, and format
  checks green; both production builds green; the storefront budget and
  built-server verification green.
- Only disposable test infrastructure was used; `restaurant_engine` and
  `restaurant_engine_uat` were neither contacted nor modified.

**M4G-B is the next undelivered slice** and needs its own discovery and
authorization. M4G-C and M4G-D remain not started, Milestone 4 remains
complete, and **Milestone 5 remains unstarted**.

## Milestone 2 delivery decision (2026-07-16)

The approved M2 architecture (proposal + revision + final addendum)
subdivides M2 into six independently reviewed sub-milestones, one PR each,
strictly sequential:

| Sub                                           | Scope                                                                                                                                                                                                                                             | State                              |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **M2A** — Identity & session core             | users/sessions/audit_events schema; Argon2id; opaque hashed-token sessions; login/logout/session; fail-closed CSRF; uniform-failure backoff; audit recorder; bootstrap CLI (ADR-010)                                                              | **Complete** (2026-07-16)          |
| **M2B** — Tenancy model & capabilities        | businesses (the tenant aggregate, ADR-012), memberships, capability policies (ADR-011), service-layer authorization, lifecycle + platform endpoints, enriched session view, isolation matrix v1                                                   | **Complete** (2026-07-17)          |
| **M2C** — Tenant resolution & isolation       | parser-level host normalization, two-scope trusted-host policy, direct-subdomain slug resolution, reserved-slug policy, public `site` endpoint, neutral public-failure semantics, consolidated isolation matrix (ADR-013)                         | **Complete** (2026-07-17)          |
| **M2D** — Onboarding, recovery & entitlements | invitations (role ceiling, owner bootstrap, existing-user acceptance), platform-issued password-reset tokens, feature entitlements (registry seeded `online_ordering`), platform + business audit list APIs with typed safe projections (ADR-014) | **Complete** (2026-07-18)          |
| **M2E** — Control-center auth UI              | login/session UI, guards, accept-invitation and reset pages, dev proxy                                                                                                                                                                            | **Complete** (2026-07-18, ADR-015) |
| **M2F** — Platform UI & E2E                   | platform area UI, deep-import lint hardening, first Playwright journeys + CI e2e job                                                                                                                                                              | **Complete** (2026-07-19, ADR-016) |

## Milestone 1 delivery decision (2026-07-14)

Approved subdivision into three independently reviewable sub-milestones:

| Sub-milestone                               | Scope                                                                                                                                                                                               | State                     |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **M1A** — Backend and PostgreSQL foundation | FastAPI factory, settings, correlation IDs, structured logging, error envelope (ADR-008), sync SQLAlchemy core (ADR-007), compose database, Alembic baseline, health probes, backend tests + CI job | **Complete** (2026-07-15) |
| **M1B** — Frontend application shells       | Next.js storefront shell, React/Vite control-center shell, neutral placeholder pages, frontend lint/typecheck/test/build                                                                            | **Complete** (2026-07-15) |
| **M1C** — API contract and CI integration   | Deterministic OpenAPI export, generated TypeScript client + facade (ADR-009), drift check, integrated CI matrix, one-command stack + clean-clone verification                                       | **Complete** (2026-07-15) |

M1A ∥ M1B are independent; M1C depends on both. CI gained the backend job
with M1A (untested application code must not merge); the integrated matrix
lands with M1C.

## Commercial roadmap reconciliation (2026-07-23)

Documentation-only reconciliation performed during Milestone 3 (M3F still
open; **not** a milestone-completion or implementation change). It **adds no
application code, API, schema, or dependency**. Its purpose is to remove
vagueness from the future commercial commitments so that ordering,
promotions, campaigns, and external publishing have explicit boundaries
before any of them is built.

What it does:

- **Strengthens** the existing ordering commitments (M6 cart/checkout, M7
  restaurant order operations) so Restaurant Engine delivers order
  management at least equivalent to the Grocery platform and better adapted
  to active restaurant operations — without weakening any existing boundary.
- **Adds** three post-pilot commercial-growth milestones — **M9** promotion
  and discount foundation, **M10** Marketing Center and storefront
  campaigns, **M11** Facebook Page publishing — each with recorded scope,
  domain boundaries, and deferral lines.
- **Records** the long-term owner Control Center organization, the
  cross-milestone dependency sequencing, the module boundaries between
  ordering, promotion pricing, campaign presentation, and channel delivery,
  and the verification surface those capabilities will eventually need.

Authority. The blueprint (`00_RESTAURANT_ENGINE_BLUEPRINT.md`) §19 remains
authoritative for Milestones 0–8 and is unchanged. M9–M11 extend the
roadmap beyond the blueprint's evidence-gated "after pilot" list; they
inherit the same milestone discipline (demoable, testable, documented,
mergeable) and each still opens as its own architecture review before
implementation. The extension is to be folded into the blueprint at a future
review; until then this section is the reconciliation of record. No completed
milestone record or historical wording elsewhere in this file was altered.

## Milestone 0 — Architecture and repository contract

**Deliver:** governing documents committed; README and orientation; handbook
docs 00–08; ADR template and bootstrap ADRs (001–006); `.gitattributes`,
`.gitignore`, `.editorconfig`, `.env.example`; runtime and dependency-version
policy; pnpm workspace and root command contract; Python project/tooling
contract; TypeScript/Ruff/ESLint/Prettier/mypy/pytest configuration
baselines; CI skeleton appropriate to existing files; Windows and Linux
workflow; contribution and feature-branch workflow.

**Exit criteria:** architecture and scope are understandable from the
repository; runtime/tool versions and commands are defined; repository
configuration is internally consistent; applicable documentation and
configuration validation passes; no application or product-domain behavior
exists.

## Milestone 1 — Platform foundation

**Deliver:** FastAPI skeleton with `/api/v1`, error envelope, request
correlation IDs, structured settings and logging, `/health/live` and
`/health/ready`; PostgreSQL via Docker Compose; Alembic baseline; Next.js
storefront shell and React control-center shell with neutral placeholder
pages; deterministic OpenAPI export and the generated TypeScript client
pipeline; application smoke tests; production builds; CI expanded to run
them.

**Exit criteria:** production builds succeed; migration runs from an empty
database; API client generation is deterministic; no copied cross-app
contracts; a new developer can start the stack with one documented command
and see the health endpoints.

## Milestone 2 — Identity, tenancy, and onboarding

Secure sessions, users, memberships, capability policies, restaurant
lifecycle, tenant resolution, feature entitlements, onboarding API/UI, audit
foundation. **Exit:** isolation matrix passes; platform admin can onboard;
owner logs in only to assigned restaurant; suspension behaves correctly.

## Milestone 3 — Catalog and media

Categories, items, modifiers, integer money, availability, sorting, featured
policy, safe media adapter/upload, restaurant menu UI, public menu API.
**Exit:** constraints and service rules pass; mobile menu administration
works; cross-tenant media and catalog tests pass.

## Milestone 4 — Storefront composition and publication

Section registry, validated configs, design governance, draft/publish/
history, server-rendered storefront, SEO basics, and Unicode/complex-script
rendering verification — the blueprint's "English/Bengali rendering
verification", read prospectively per the 2026-07-29 universal-positioning
ruling (ADR-021): Bengali is the required initial complex-script fixture,
not a market-specific product boundary. **Exit:** invalid config cannot
save; published config always renders; draft is never public;
performance/accessibility budgets pass.

## Milestone 5 — Hours and pickup readiness

Weekly hours, exceptions, fulfillment settings, pickup-slot service, hours UI
and storefront display. **Exit:** DST, closure, lead-time, and next-opening
tests pass; public availability derives from structured settings.

## Milestone 6 — Cart and guest pickup ordering

Modifier picker, cart schema/versioning, server price validation, idempotent
checkout, order snapshots, tracking token, transactional outbox,
confirmation. **Exit:** retries do not duplicate; stale items fail
gracefully; totals are authoritative; orders survive menu edits; end-to-end
checkout passes.

**End-to-end commercial ordering (strengthened 2026-07-23).** This milestone
delivers a commercially usable pickup-ordering foundation on the
restaurant's **own branded website/domain** — the customer never leaves it
for a marketplace. The customer half must cover:

- **Fulfillment:** pickup-first; **cash or pay-at-store first** — no online
  card payment is required to place an order in this milestone.
- **Checkout capture:** customer name and contact, item-level instructions,
  and order-level instructions, all length-limited plain text (never
  operational instructions to the system, per blueprint §7.7). Consent is
  captured as **two separate, independently recorded choices**: one for
  transactional order updates, a distinct one for future promotional
  messages — never a single blended opt-in.
- **Server-authoritative pricing:** the server recalculates every price;
  client totals are display hints only; money is **integer minor units**
  (per-tenant currency lives on the business, ADR-017 D8); modifier price
  deltas are explicit; availability and modifier rules are revalidated at
  submission.
- **Idempotent submission:** an idempotency key makes retries and
  double-taps produce one order; order creation and the outbox notification
  commit together.
- **Immutable order snapshot** — a completed order preserves, and never
  re-derives from the live menu: order number; item display names; base
  prices; quantities; modifier selections and their price deltas; item
  instructions; order instructions; taxes; subtotal and final total; and the
  customer and fulfillment information the order requires. It also **reserves
  the promotion/discount snapshot fields** (applied promotions, discount
  amounts) so that when M9 lands, historical orders already carry them and
  never change retroactively. Later menu-price or promotion edits must not
  alter a past order.
- **Customer confirmation and status tracking** on the restaurant's own
  site via a high-entropy tracking token (not a sequential id).
- **Cancellation** is handled in this initial ordering release; **refunds**
  are deferred to when online payments are introduced (post-pilot).

**Release boundaries preserved (must not expand here):** pickup first; cash
or pay-at-store first; no online card payment requirement; no delivery
dispatch; no POS integration; no marketplace redirect; customers stay on the
restaurant's own branded website. The ordering interface must be responsive,
mobile-friendly, and fast enough for real use — never reduced to a generic
CRUD table. Notifications to the customer (accepted, prep estimate, ready,
rejected, cancelled) are wired here where a channel exists and otherwise
land with the channel milestone; message content is owned by the Orders
domain, not by any campaign.

## Milestone 7 — Restaurant order operations

Order board, guarded status commands, polling, notifications with user
control, audit timeline, operational filtering. **Exit:** permissions and
state machine pass; concurrent staff actions cannot corrupt state; customer
tracker reflects transitions; mobile/tablet usability verified.

**Active-restaurant order operations (strengthened 2026-07-23).** The staff
half must be usable during a live service, not a generic admin table:

- **Prominent real-time new-order alert** so staff never miss an incoming
  order.
- **Controlled states**, the blueprint §7.7 machine surfaced in operational
  language — **New/Pending** (the submitted state), **Accepted**,
  **Preparing**, **Ready**, **Completed**, plus terminal **Rejected** and
  **Cancelled**. Every transition is permission-checked, validated against
  the current state, timestamped, and audited; status is never an arbitrary
  string patched through a generic endpoint.
- **Accept or reject** an order (authorized staff); **set and update an
  estimated preparation time**.
- **Live operational order board** with clear status columns, order age,
  promised pickup time, overdue indicators, priority indicators, and
  prominent new-order visibility.
- **Order detail** showing order number; items and quantities; modifiers;
  item-level and order-level instructions; customer name and contact; pickup
  time; payment status where applicable; order source; promotion and
  discount details (from the M9 snapshot when present); and the complete
  status history.
- **Print-friendly and kitchen-display-friendly tickets.**
- **Search and filters** by order number, customer, date, status, and
  fulfillment state; **customer-linked order history**.
- **Customer confirmation and status tracking** on the restaurant's own
  website (the M6 tracker), reflecting each transition; customer
  notifications for acceptance, prep estimate, ready, rejection, and
  cancellation land when the relevant channel becomes available.
- **Temporary ordering pause/resume** with a customer-visible explanation,
  an optional resume time, and correct restaurant-timezone handling; plus
  restaurant-hours and order-acceptance enforcement.
- **Safe concurrency** when several staff devices update one order, with
  controlled, auditable transitions; **role/capability controls** for
  viewing orders, updating preparation state, cancelling, and performing
  future refunds.
- **Dashboard metrics:** today's order count, sales, average order value,
  popular items, cancellation/rejection rate, and preparation-time
  performance.

The order-management interface must be responsive, mobile-friendly, and fast
enough for active restaurant use, and must not be reduced to a generic CRUD
table. **Refunds are excluded here** (they arrive with online payments,
post-pilot); cancellation is in scope.

## Milestone 8 — Production hardening and pilot

Production compose, wildcard domains/TLS, backup/restore, monitoring,
alerting, security review, rate limits, MFA for platform admins, runbooks,
pilot onboarding checklist. **Exit:** clean-host deployment and restore drill
succeed; critical Playwright suite passes against staging; no default
secrets; first pilot supportable.

## Milestone 9 — Promotion and discount foundation

An explicit, server-authoritative promotion/discount domain that integrates
with menu presentation, campaigns, cart pricing, checkout, orders, and
reporting. A discount is never modelled as unvalidated text, and never as a
destructive replacement of an item's normal price.

**Four distinct concepts, kept separate:**

- **Base menu price** — the restaurant's normal item price (unchanged by any
  promotion).
- **Promotion** — the eligibility and pricing rule.
- **Campaign** — the customer-facing content and distribution that advertises
  a promotion (M10). A campaign may advertise a promotion but **must never be
  trusted to calculate prices**.
- **Coupon code** — an optional activation method for a promotion, not the
  promotion itself.

**Initial promotion types (commercially usable scope):** percentage discount
on selected items; percentage discount on selected categories; percentage
discount on an eligible order; fixed-amount discount on an eligible order;
scheduled item sale price or fixed reduction.

**Explicitly deferred** unless already planned: buy-one-get-one, multi-item
bundles, loyalty rewards, gift cards, personalized AI offers, paid-membership
discounts, delivery-specific promotions, advanced customer segmentation.

**Owner configuration** includes: internal promotion name; customer-facing
label; promotion type; percentage / fixed-amount / sale-price value as
appropriate; eligible restaurant, items, or categories; minimum qualifying
subtotal where applicable; optional maximum discount cap;
restaurant-timezone start and end date/time; active / paused / ended /
archived states; automatic or coupon-code application; redemption limits
where supported; a clear eligibility summary and preview; an immediate
pause/disable control; and audit + change history.

**Menu-workspace integration (convenience, not a second pricing engine).**
From an item row or the item editor the owner can start an item-level
promotion via a contextual action (e.g. **Put on sale**, **Create
discount**, **Manage promotion**) and enter a validated percentage, fixed
reduction, or sale price plus an optional schedule. This convenience
workflow **creates or links a real promotion record**; it must not overwrite
the item's base price and must not create separate pricing logic inside the
Menu UI. The Menu workspace shows the normal/base price, any active sale
price or discount, a scheduled-promotion indicator, start/end timing, the
promotion status, and a link to manage the full promotion. Category-wide and
order-wide promotions are managed primarily from the **Marketing Center**
(M10), which is the canonical place to view, schedule, pause, end,
duplicate, and report on all promotions.

**Cart and checkout behaviour** (applied during the customer's real cart and
checkout, not merely advertised): server-authoritative price and discount
calculation; money in integer minor units; eligibility recalculated whenever
the cart changes and **revalidated again at order submission**; the browser
is never trusted for the final discount amount; clear cart/checkout lines for
subtotal, promotion/discount, tax, and final total; the customer sees which
promotion applied and a clear message if it becomes invalid, expires, or no
longer qualifies before submission; a discount can never take a payable total
below zero; deterministic rounding; explicit handling of modifier price
deltas; **explicit, legally configurable placement of discounts relative to
tax** (never an unreviewed tax assumption buried in UI code); tenant
isolation for every promotion and calculation; idempotent placement that
never applies or redeems a promotion twice. The completed order stores an
**immutable promotion snapshot** — promotion identifier, name/label, type,
rule summary, discount per eligible line where applicable, total order
discount, and resulting totals — and later changes to a menu price or the
promotion never alter historical orders.

**Stacking and conflicts (must not be left undefined).** For the initial
release, stacking is **disabled** unless a later architecture explicitly
supports it; when several automatic promotions could apply, exactly one is
chosen by a deterministic rule (a single best-eligible promotion, or an
explicit non-stacking priority model). Coupon-vs-automatic conflicts are
resolved clearly, and the customer sees which promotion won and why another
could not be combined. Staff-entered complimentary discounts or manual price
overrides are a **separate future capability** and must never be silently
mixed into customer promotions. (The precise initial conflict policy is to be
fixed in this milestone's architecture review; it must not ship undefined.)

## Milestone 10 — Marketing Center and storefront campaigns

The reusable campaign foundation — content, scheduling, attribution, and
lifecycle — plus the first onsite placements. This is the earliest milestone
that delivers the Marketing Center on top of the M9 promotion foundation, so
the storefront pop-up workflow lives here rather than as an uncontrolled
modal or vague "website promotions."

**Campaign foundation and lifecycle:** create, edit, duplicate, preview,
schedule, pause, resume, end, and archive, with lifecycle states **Draft,
Scheduled, Active, Paused, Ended, Archived**. A campaign carries a title and
customer-facing message; artwork/media; optional featured menu items; an
optional linked promotion; and a CTA label and destination.

**Storefront placements:** promotional pop-up/modal; announcement bar; and a
homepage promotional section where supported. With restaurant-timezone
scheduling; desktop and mobile preview; display-frequency rules (once per
session, once per visitor, once per defined period); dismissal behaviour;
basic audiences (all / new / returning visitors where technically
supported); accessible and responsive presentation; immediate emergency
unpublish; campaign history and audit events; and initial metrics
(impressions, dismissals, CTA clicks, promotion activations, and attributable
orders/conversions where ordering data supports reliable attribution).

A campaign **may be informational and carry no discount.** When a pop-up
advertises a discount it **must reference a valid M9 promotion**, and the
pop-up itself contains **no independent pricing calculation.**

**Pop-up-to-checkout discount journey** (required end-to-end for a discount
campaign): (1) the customer sees the campaign on the storefront; (2) clicks
the CTA; (3) is taken to the relevant item, category, menu, or ordering
surface; (4) the linked promotion is activated automatically where
configured, or the coupon code is clearly provided; (5) eligible items are
added to the cart; (6) the **server** evaluates the promotion; (7) cart and
checkout display the applied discount; (8) order submission revalidates it;
(9) the completed order stores the promotion and discount snapshots; (10)
campaign attribution is recorded without trusting client-supplied financial
values. The owner can preview the whole relationship
(`Campaign → promotion → eligible menu selection → expected customer
destination`) before publishing.

**Publish-time safety:** prevent, or clearly warn about, publishing a
discount campaign when its promotion is missing, paused, or has empty
eligibility; when the promotion expires before the campaign; or when the
campaign and promotion schedules conflict.

## Milestone 11 — Facebook Page publishing

A feature-gated external channel adapter, delivered after or alongside the
M10 campaign foundation. It publishes a Marketing Center campaign to an
**authorized restaurant-owned Facebook Page** and no further.

**Scope:** connect a restaurant-owned Facebook Page through the supported
Meta authorization flow; select the correct managed Page; secure, encrypted,
tenant-isolated credential/token handling; create a Facebook post from a
campaign with Facebook-specific copy and preview, campaign artwork or dish
image, and optional promotion messaging; a CTA/link back to the restaurant's
own storefront, item, campaign landing destination, or ordering page, with
campaign attribution in the link; publish now and schedule for later subject
to supported Meta API capabilities; publication status, Facebook post
identifier and link, and failure details; safe retry that avoids duplicate
posts; publication history; disconnect and revoke controls; and audit events
for connection, disconnection, publishing, scheduling, failure, and retry.
Operationally it must account for Meta permissions, Meta app review, API
version changes, rate limits, token expiration, and revoked Page access.

**Authority stays local:** a Facebook post may advertise the same promotion
as an onsite campaign, but Facebook **never** determines checkout eligibility
or the discount amount — the Restaurant Engine backend remains authoritative.

**Facebook publishing means an authorized restaurant Facebook Page only.** It
does **not** automatically include personal-profile posting, Facebook Group
posting, paid Facebook advertising, Instagram publishing, automated comments
or engagement, or other unsupported social automation — each of those is a
separate decision.

## After pilot evidence

Sequenced (step 8 of the dependency order below): later notifications and
customer messaging, online payments, refunds, delivery, POS integrations,
advanced targeting, and advanced reporting — together with customer
accounts, reservations, custom domains, billing, multi-location, and other
integrations. Each is prioritized on restaurant/customer evidence and opened
as an architecture discussion, not an assumed promise. The M9–M11 commercial
milestones above are the promotion, campaign, and channel work that these
depend on and precede.

## Future owner Control Center organization

The long-term owner interface should be organized into a commercial
restaurant Control Center with these areas: **Dashboard, Orders, Menu,
Customers, Marketing, Storefront, Media, Staff, Reports, Settings.** The
current M3F menu interface is an acceptable functional foundation and is
**not** to be redesigned during this documentation reconciliation.

The **Marketing Center** should eventually let the owner create promotional
content once and select eligible channels — storefront pop-up, announcement
bar, homepage promotion, Facebook Page, later email, and later
consent-based SMS. These channels **do not ship simultaneously**; each
arrives with its milestone. The **Menu** workspace may offer convenient
_Put on sale_ / _Create discount_ actions, but **Marketing remains the
canonical** promotion and campaign management area.

## Required architectural sequencing

The following is a **dependency order** (what each capability builds on), not
a promise that every step is a separate calendar release. Milestone numbering
delivers the ordering foundation (M6) and the base order board (M7) ahead of
the pilot (M8); the promotion, campaign, and Facebook work follows as M9–M11,
with kitchen-workflow and cross-channel refinements layering on per this
graph.

1. Cart, checkout, order-pricing, and immutable order-snapshot foundation.
2. Server-authoritative promotion and discount rules.
3. Reusable campaign, content, scheduling, attribution, and lifecycle
   foundation.
4. Onsite placements, including pop-ups and announcement bars.
5. Reliable linkage from campaign to promotion and checkout.
6. Restaurant live-order board and kitchen workflow.
7. External channel adapters such as Facebook Page publishing.
8. Later notifications, customer messaging, advanced targeting, online
   payments, refunds, delivery, POS integrations, and advanced reporting.

## Cross-domain boundaries

Campaign presentation, promotion pricing rules, ordering, and Facebook
delivery remain **separate modules with explicit integration boundaries**.
Campaign content advertises but never prices; promotion rules are the only
authority on eligibility and discount amount; orders own their immutable
snapshots; channel adapters (Facebook and later others) only deliver and
attribute. **Facebook-specific concerns must not leak into the core campaign
or promotion domains.**

## Future verification coverage

The roadmap makes room for — but this reconciliation does **not** implement —
future verification of: tenant isolation; percentage and fixed-amount
calculations; integer-money rounding; minimum-order and maximum-discount
rules; item/category eligibility; modifier treatment; promotion start/end
boundaries in the restaurant timezone; pause and expiry behaviour;
coupon-vs-automatic conflicts; non-stacking behaviour; cart recalculation;
server-side checkout revalidation; idempotent order creation/redemption;
immutable order snapshots; campaign/promotion schedule mismatches; the
pop-up-to-checkout customer journey; Facebook retry without duplicate
publication; order-state concurrency; role/capability enforcement; and
audit-event coverage.
