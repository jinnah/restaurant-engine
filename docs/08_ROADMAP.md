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

| Milestone                                                      | State                                                  |
| -------------------------------------------------------------- | ------------------------------------------------------ |
| M0 — Architecture and repository contract                      | **Complete** (2026-07-14)                              |
| M1 — Platform foundation                                       | **Complete** (2026-07-15)                              |
| M2 — Identity, tenancy, and onboarding                         | **Complete** (2026-07-19)                              |
| M3 — Catalog and media                                         | **Complete** (2026-07-23)                              |
| M4 — Storefront composition and publication                    | **Complete** (2026-07-30)                              |
| M4G — Curated storefront design and motion (extension)         | **Complete** (2026-08-01; M4G-A–M4G-D, ADR-024)        |
| M5 — Hours and pickup readiness                                | **Complete** (2026-08-02; M5A–M5E, ADR-025)            |
| M6 — Cart and guest pickup ordering                            | **In progress** (M6A–M6C complete 2026-08-02, ADR-026) |
| M7 – M8 — Order operations, pilot                              | Not started                                            |
| M9 – M11 — Commercial growth (promotions, campaigns, Facebook) | Not started (planned; reconciliation 2026-07-23)       |

## Milestone 6 delivery decision (2026-08-02)

The approved M6 architecture (ADR-026, with binding rulings D1–D14 as
amended in review) subdivides M6 into four independently reviewed
slices, one PR each. M6B depends on M6A; M6C depends on M6A and M6B;
M6D depends on all of them.

| Slice                                  | Scope                                                                                                                                                                                                 | State                              |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **M6A** — Orders domain foundation     | order/idempotency/outbox tables + migration, pure pricing core over the catalog checkout view, transactional idempotent placement with D3 throttling, `POST /public/orders`, D9 self-origin, contract | **Complete** (2026-08-02, ADR-026) |
| **M6B** — Public tracking and the gate | tracking GET + customer cancel + pickup-slots endpoint, `ordering_enabled` on the availability projection, `HeroAction.ORDER_ONLINE` + renderer arm, isolation matrix                                 | **Complete** (2026-08-02, ADR-026) |
| **M6C** — Storefront ordering UI       | cart island + persisted schema, modifier picker, `/order` checkout (consents, slots, honest failure states), confirmation + tracker, dev-forwarder POST, allowlist/budget updates                     | **Complete** (2026-08-02, ADR-026) |
| **M6D** — E2E and close-out            | the CC fulfillment-throttle field, blueprint journey 4 (order despite a simulated retry) + cancellation and stale-item journeys, responsive/a11y acceptance, exit-criteria verification               | Not started                        |

### M6C close-out (2026-08-02)

M6C delivered **the storefront ordering surface** — the third
Milestone 6 slice and the storefront's first client JavaScript beyond
the error boundary. No backend change; the contract stays at 78
operations; **zero new runtime dependencies** (D13).

**The five named islands.** The cart is a pure, versioned client value
persisted in localStorage under the tenant origin (isolation is
structural — no tenant key exists; anything unrecognized drops cleanly
to empty), with identical choices merged and the contract bounds
mirrored. The modifier picker is a native `<dialog>` enforcing the
projection's own selection rules locally while the server stays
authoritative. `/menu` reads the availability projection for the D12
gate — three backend reads now, the home route's M5D precedent — and
renders the add-to-order affordance on orderable items
(`is_orderable` finally renders) plus the cart link only while
ordering is on; off, the page is byte-identical to the pre-ordering
menu. `/order` is the checkout surface, server-gated on
`ordering_enabled` with the one neutral 404 (D10): the two independent
never-pre-checked consents (D7), the required `expected_total_minor`
(D8), ASAP-or-scheduled from the public slot listing, and honest
renderings of all four typed 409s — `cart_stale` marks lines,
`price_changed` adopts the authoritative total for a deliberate retry,
`slot_unavailable` refreshes the listing, `idempotency_key_reused`
mints a fresh key (D2: the key is held per submission content).
`/order/track/{token}` is published-chrome-gated only — deliberately
NOT entitlement-gated (D10 as amended), noindex — polling at 15 s,
stopping on terminal statuses, with the two-step D11 cancellation.

**Transport and SEO.** Islands fetch relative same-origin paths; the
dev-only forwarder gains POST for `/api/v1/public/` only, forwarding
the body and browser-context evidence verbatim through its own
`node:http` leg — the read-only SSR tenant transport is untouched and
production stays disabled. Decision recorded: the ordering routes are
transactional and their existence is a live entitlement fact, so they
are noindex, robots-disallowed (the `/order` prefix), and never in the
sitemap, which stays exactly `/` and `/menu`.

**Budget, and a measurement discovery.** The ADR-021 ceiling method is
unchanged and green (456,694 B vs 502,201 B, all four routes).
Discovered while extending the measurement: `rootMainFiles` omits the
app-router client-components chunk (~58 KB) every route has always
loaded — the recorded baseline under-measured the real first load by
that constant on every route, before and after M6C alike. The ceiling
keeps its recorded meaning; the budget script now additionally
measures and reports each route's marginal island JavaScript (the
ADR-024 §11 precedent, no threshold): `/menu` 9,703 B, `/order`
16,332 B, `/order/track` 7,429 B, home 0. A corrected-baseline ADR-021
amendment is the recorded candidate, for review.

**Verification.** Storefront **143** (from 78); renderer **165** (from
163 — the `MenuListing.itemAction` seam, absent → byte-identical);
api-client 115, control-center 480, backend 1,301 unchanged and green;
contract byte-current; builds green; built-server verification
extended to the ordering surface (the hero "Order online" CTA on the
wire, menu at exactly three reads, `/order` at two, track at one with
no entitlement read, robots Disallow, sitemap unchanged); `pnpm e2e`
green with full disposable cleanup.

Merge evidence (PR #56): reviewed head
`7e7db449188210f145bef287cd3649fc3a1c77f9` (the first pushed head
`44217c85` failed exact-head CI run `30766259767` on the CSS
regression suite — its fixtures needed the new routes; the follow-up
commit extended them), merged to `main` as
`84a533cf28c7886ed25fe4b5dde3cb69549cf80a` (ordered parents `385ac2b1`
then the reviewed head; merge tree `164ea191` equal to the reviewed
head tree). Exact-head CI run `30766483548` and exact-merge push CI
run `30766673037` both completed successfully — five jobs green, zero
artifacts, attempt 1.

**Boundary.** No ordering e2e journeys, no CC fulfillment-throttle
field, no responsive/a11y acceptance for the ordering surfaces (M6D);
no outbox worker (D14). Milestone 6 is not complete until the §19 exit
criteria are proven at M6D. The four retained risks stand unchanged.

### M6B close-out (2026-08-02)

M6B delivered **public tracking, customer cancellation, the slot
listing, and the ordering gate** — the second Milestone 6 slice. No
schema change; contract **75 → 78**.

**Three public routes join the ordering surface.**
`GET /public/orders/{tracking_token}` answers by token possession plus
the tenant Host, both required, compared digest-only (D4), with the
PII-free `PublicOrderView` snapshot projection — a tracking URL is
shareable by design, so it never returns the name, phone, email,
consents, or instructions the order stores.
`POST /public/orders/{tracking_token}/cancel` (D11) is legal only from
`submitted`, runs under the Business lock so slot release serializes
with placement counting, is idempotent on an already-cancelled order,
refuses with `409 invalid_state` past `submitted`, and writes the
customer-actor status event plus the NULL-actor
`order.cancelled_by_customer` audit event.
`GET /public/pickup-slots` is the first real exposure of the M5 slot
service, bounded by the shared `MAX_PUBLIC_SLOTS` (100) policy and
D10-gated exactly like placement. Tracking and cancellation are
deliberately **not** entitlement-gated (D10 as amended): an order
already placed stays trackable and cancellable after the platform
revokes ordering — proven by the entitlement-revocation survival test.

**The D12 gate ships as a live public fact.** `PublicPickup` gains
`ordering_enabled` (`online_ordering` entitlement AND
`pickup_enabled`), computed per request and never frozen into
published content, at zero request cost — the home render has read the
availability projection since M5D. `HeroAction` gains the reserved
`order_online` member; the renderer renders it as ordering navigation
only when the gate is on and degrades to the plain menu link otherwise
(default off, so the workspace preview never fabricates an ordering
affordance). One recorded pull-forward from M6D: the composer's hero
dialog accepts and offers "Order online" with honest hint copy — the
widened contract type forced the dialog to handle stored values, and
the enum-and-handlers-together rule requires offering what is handled.
The public-surface invariant pin grows to exactly the two reviewed
unsafe routes, each carrying both the Host resolver and the
browser-context check.

**Verification.** Backend **1,301** (from 1,290); api-client **115**
(from 112); renderer **163** (from 161); storefront 78 and
control-center 480 unchanged and green; contract byte-current;
first-load JavaScript unchanged at 456,547 B; built-server
verification green; `pnpm e2e` green with full disposable cleanup.

Merge evidence (PR #54): reviewed feature head
`a2030175cf74a04b1954d0395862cf2437229b67`, merged to `main` as
`9e9f45768da0c2b262df3e3f7d8040878f675b14` (ordered parents
`ffacb354` then the reviewed head; merge tree `63b3a0ef` equal to the
reviewed feature-head tree). Exact-head PR CI run `30763611800` and
exact-merge push CI run `30763807914` both completed successfully —
five jobs green, zero artifacts, attempt 1.

**Boundary.** No storefront ordering UI — cart, modifier picker,
`/order`, tracker (M6C); no CC fulfillment-throttle field and no
ordering e2e journeys (M6D); no outbox worker (D14). The four retained
risks stand unchanged.

### M6A close-out (2026-08-02)

M6A delivered the **orders domain foundation and guest placement** —
the first Milestone 6 slice and the first schema change since M5A. One
additive migration (`e7a2c94d51b8`) lands `orders`, `order_lines`,
`order_line_options`, `order_status_events`, `idempotency_keys`, the
platform-global `outbox_messages`, and the nullable
`fulfillment_settings.max_orders_per_slot` column — discharging
ADR-025's D3 deferral (hours owns the setting; the orders checkout
counts non-cancelled orders per promised slot under the Business lock;
existing rows gain no cap and the delivered M5C form stays valid).

**Placement is one transaction, and totals are authoritative.** The
pure pricing core validates and reprices the whole cart against the
explicit `catalog.checkout_view` interface (orders never touches
catalog's models), applies the public projection's own orderability
formula at order time, and collects every problem before failing —
`409 cart_stale` names each stale line, `409 price_changed` carries the
real totals against the required `expected_total_minor` (D8), and
`409 slot_unavailable` covers ASAP-unavailable, an invalid or off-grid
scheduled instant (recomputed through the M5 slot service, never
trusted from a list shown earlier), and a full slot (D3). Under the
Business row lock (D5) the order, the FK-free snapshot (D1 — display
names, prices, bare provenance UUIDs), the `→ submitted` event, the
`order.placed` outbox message (D14 — written transactionally, no
worker), the idempotency row (D2 — a replay returns the current
representation of the one stored order; key reuse with a different
payload is `409 idempotency_key_reused`; the concurrent-duplicate race
resolves to the winner's order), and the NULL-actor audit event commit
together. Tracking tokens are 256-bit and digest-stored, disclosed
exactly once in the placement response (D4); consents are two
independent booleans and the M9 promotion snapshot columns plus
`tax_minor` exist CHECK-frozen (D6/D7); `placed_at` UTC plus
`business_timezone` records the ADR-025 timestamp pair.

**The first unsafe public route, deliberately.**
`POST /api/v1/public/orders` is host-resolved with the one neutral 404
for every ineligible cause — including a missing `online_ordering`
entitlement or disabled pickup (D10, through the first actor-free
entitlement primitive) — and guarded by the fail-closed browser-context
check extended with **self-origin** acceptance (D9 as amended in
review: the Origin's host must equal the request's own Host; a
tenant-family rule was rejected as cross-tenant-permissive on legacy
browsers). The public-surface invariant test now pins the reviewed
unsafe set exactly and proves both guards sit in the route's dependency
graph. Contract **74 → 75** (`public_order_place`); the public client
facade gains `placeOrder()`.

**Verification.** Backend **1,290** (from 1,245); api-client **112**
(from 109); every frontend suite unchanged and green (renderer 161,
storefront 78, control-center 480); contract byte-current; first-load
JavaScript unchanged at 456,547 B; built-server verification green;
`pnpm e2e` **25 passed** with full disposable cleanup.

Merge evidence (PR #52): reviewed feature head
`f4f73f8470c5ac6925ce9b26ee74ad03f023c632`, merged to `main` as
`77f2b73e8eb6d4c5c64c2d3ae05ec80945b519b9` (ordered parents
`b01c93f1b003` then the reviewed head; merge tree `34bb67a0` equal to
the reviewed feature-head tree). Exact-head PR CI run `30761169052` and
exact-merge push CI run `30761377392` both completed successfully —
five jobs green, zero artifacts, attempt 1.

**Boundary.** No tracking, cancellation, slot listing,
`ordering_enabled` fact, or `HeroAction` member (M6B); no storefront
ordering UI (M6C); no CC throttle field or ordering journeys (M6D); no
outbox worker (D14), no tax computation (D6), no per-IP rate limiting
(M8). The four retained risks stand unchanged.

## Milestone 5 delivery decision (2026-08-01)

The approved M5 architecture (ADR-025, with binding rulings D1–D7)
subdivides M5 into five independently reviewed slices, one PR each. M5B
and M5C depend on M5A; M5D depends on M5A and M5B; M5E depends on all of
them.

| Slice                         | Scope                                                                                                                                                                                                                   | State                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **M5A** — Hours foundation    | `business_hours` / `schedule_exceptions` / `fulfillment_settings` + migration, pure DST-safe timekeeping/availability core, admin API, platform timezone command (D2), capability, audit actions, contract regeneration | **Complete** (2026-08-01, ADR-025) |
| **M5B** — Public availability | `GET /api/v1/public/availability`, neutral failure semantics, `no-store` (D4), isolation tests                                                                                                                          | **Complete** (2026-08-02, ADR-025) |
| **M5C** — Hours workspace UI  | `/businesses/:id/hours`: weekly editor with DST-gap warning, exceptions, fulfillment settings                                                                                                                           | **Complete** (2026-08-02, ADR-025) |
| **M5D** — Storefront display  | `hours` section + three renderer arms + composer control (one slice), JSON-LD hours, request-cost assertion update                                                                                                      | **Complete** (2026-08-02, ADR-025) |
| **M5E** — E2E and close-out   | journeys, per-variant acceptance for the new section, documentation, exit-criteria verification                                                                                                                         | **Complete** (2026-08-02, ADR-025) |

## Milestone 5 close-out (2026-08-02)

Milestone 5 is **complete**. M5E (the browser-level hours journeys,
per-variant acceptance for the hours section, and this close-out) is
delivered, completing the M5A–M5E progression. The blueprint §19 exit
criteria are verified:

- **DST, closure, lead-time, and next-opening tests pass.** The pure
  `hours.timekeeping`/`hours.availability` core takes `now` as an
  argument and is proven exhaustively at the unit layer (M5A): every
  minute of the New York spring-forward gap moves to the gap's end;
  fall-back openings take the earlier occurrence and closings the
  later, so the open window is the union; overnight intervals convert
  end-to-end across transitions; exceptions replace their date while
  an overnight interval still belongs to the service day that opened
  it; lead time, cut-off, and the service-day horizon govern pickup
  slots; and every next-opening scan is bounded, across
  America/New_York, America/Phoenix, Australia/Sydney, and
  Australia/Lord_Howe.
- **Public availability derives from structured settings.** The
  projection (M5B) is computed per request through the pure core from
  the D1-encoded weekly schedule, exceptions, and fulfillment policy —
  never from freeform text — and the M5E journey proves the derivation
  end to end in a real browser: hours authored in the workspace UI
  render on the anonymous tenant host with the correct live status,
  and an empty schedule renders honestly closed.

**Stated plainly, as ADR-025 requires:** the pickup-slot service is
proven by its unit suite and the public `next_pickup_at` fact — not by
a real checkout. It ships without a consumer; M6's checkout is its
genuine proving ground, and order throttling (ruling D3) is likewise
M6's obligation, alongside the UTC-plus-tenant-timezone order
timestamp rule.

Merge evidence (PR #50): reviewed feature head
`ec39d8b6615273c6c4c094d308e5798fa5057130`, merged to `main` as
`4d97eefefda4822821603ab4b885b57296b66fb9` (ordered parents
`032b06406fa2` then the reviewed head; merge tree `880bf978` equal to
the reviewed feature-head tree). Exact-head PR CI run `30752173747`
and exact-merge push CI run `30752361747` both completed successfully
— five jobs green, zero artifacts, attempt 1; both executed the full
twenty-five-test browser suite on Linux through the three-server
orchestration with proven cleanup.

The four retained risks stand open and recorded (the unexplained
dirty-navigation failure from run `30652179044`; the unidentified
local E2E non-zero exit; the unexercised accent-sweep 15-second
allowance; the keep-alive reading, unfalsified through every clean
merge-CI e2e run since PR #44). Owner-facing UAT of the hours surface
has not been conducted. No ordering, cart, or checkout behavior exists
— Milestone 6 has not begun and requires its own architecture
discovery and authorization.

### M5E close-out (2026-08-02)

M5E delivered the browser-level closure — a test-only change entirely
under `e2e/` (+389/−29 across five files), growing `pnpm e2e` from
twenty-three to **twenty-five** Playwright tests, with no application,
contract, schema, CI-workflow, or dependency change.

**The hours journey** drives every Milestone 5 surface through the
real product UI: the owner authors the all-day weekly schedule in the
M5C weekly editor (each day 00:00 to midnight-next-day through the D1
next-day choice), saves it through the full-week replacement, adds a
dated closed-all-day exception with a D6 note through the exception
dialog, composes the hours section in the M5D composer — asserting
the dialog offers **no schedule input of any kind** — saves and
publishes as the owner, and then an anonymous visitor under the tenant
host sees the section heading and intro, the live "Open now" status,
all seven day rows, the special-hours block with the exception's date
and note as plain text, and the JSON-LD `openingHoursSpecification`
carrying seven entries in the 00:00–23:59 full-day encoding. **A
second spec pins the honestly-closed state**: a published hours
section over an empty schedule renders "Closed now" with no fabricated
next opening, seven honest "Closed" rows, no special-hours block, and
no JSON-LD hours claim.

**Time-robustness is structural, not incidental** (the ADR-025 trap):
the server computes `is_open_now` from the real current instant, so
the specs never touch the browser clock — around-the-clock and
no-schedule are exactly the two states whose status is
time-independent, and instant-exact DST facts stay in the M5A unit
matrix where the clock is injected.

**Per-variant acceptance.** The seeding fixture gained an opt-in hours
option — `'open-all-day'` seeds the schedule through the real hours
API with the owner's own session and includes the section;
`'unscheduled'` includes the section over an empty schedule; callers
passing nothing submit exactly the document they always did. The
classic six-viewport responsive matrix, the editorial/express
per-variant matrix (same shared geometric floors), and the public axe
scan now run over the six-section page with a live schedule and status
line; the workspace axe scan adds the M5C hours page over its real
populated state. The hygiene watcher applies to both new specs.

**Verification.** Locally: focused hours specs green, complete suite
**25 passed** with full disposable cleanup, orchestrator regression 42
passed + 1 known Windows-symlink skip, `next-env.d.ts` restored to its
tracked baseline, and the full standing gate re-run green (backend
1,245 exit 0, every workspace suite unchanged, contract byte-current,
builds, budget, and built-server verification). Merge evidence is
recorded in the Milestone 5 close-out above.

**Boundary.** No ordering behavior (M6), no owner-facing UAT, no
production or CI-workflow change. The four retained risks stand
unchanged.

### M5D close-out (2026-08-02)

M5D delivered the **hours storefront section** — the slice that makes
structured hours visible to customers, in one change per the M4G-B
ruling so the registry, the renderer, and the composer cannot drift
apart. The `hours` section type is registered with **presentation
choices only** (ruling D5, made structural: `heading`, optional
`intro`, `show_open_now`, and a pinned field set where every
schedule-shaped smuggling attempt — `weekly`, `intervals`, `timezone`,
`hours_text`, `opens_minute`, `is_open_now` — is a 422). The schedule
itself arrives at render time from `GET /api/v1/public/availability`,
composed by the storefront application exactly as the menu section
composes with the public menu: one shared `HoursSection` renders the
weekly schedule (seven ISO rows, Monday first, honest "Closed" for
absent days), upcoming exceptions with the D6 note as plain text, and
— when the owner leaves the status line on — the server-computed
open/closed facts formatted in the **tenant** timezone, under all
three variant arms with no per-variant fork and **zero client
JavaScript**. Without availability data (the workspace preview) the
section renders its authored copy alone, the MenuSection degradation
precedent.

**The home route now costs three backend reads, visibly.** The
availability projection is read on every home render — not only when
an hours section is composed — because the Restaurant JSON-LD now
models `openingHoursSpecification` (blueprint §12.2: hours are
modeled, never decorative text): one entry per stored interval, the
D1 overnight case in schema.org's closes-before-opens convention, a
full 00:00–24:00 day stated as 00:00–23:59, and an empty schedule
claiming nothing at all. Exceptions are deliberately not claimed in
JSON-LD (transient overrides rot in a crawler's index). The
built-server verification's exact-cost assertion moved from two to
three in the same slice; `/menu` stays at two, asserted. The
availability fetch rides the tenant transport and stays `no-store`
end to end (ruling D4) — the per-request React.cache memo lives for
exactly one server request and is not a cache across requests. In the
control center, the composer offers Hours with heading/intro/status
fields and **no schedule input of any kind**; the exact full-document
payload is pinned by test.

**Verification.** Backend **1,245** (from 1,240; the data-free pin,
the projection shape at the unit layer, and the published projection
over the wire); storefront-renderer **161** (from 146; the pure
formatting helpers at the D1 edges, the section under every variant
arm with a single `h1`, honest empty states, markup-stays-text);
storefront **78** (from 70; the unconditional third read, its failure
as the generic error, JSON-LD hours including the overnight and
full-day encodings and the empty-schedule omission); control-center
**480** (from 478; the presentation-only seed and the exact composer
payload); api-client **109** unchanged. Contract regenerated: **74
operations unchanged**, new component schemas only, drift check
byte-current. First-load JavaScript unmoved at **456,547 B**;
delivered CSS measured 11,342 B per route (diagnostic, no threshold —
ADR-024 §11). Full gate green including the built-server verification
and `pnpm e2e` **23 passed** with full disposable cleanup.

Merge evidence (PR #48): reviewed feature head
`26e141ae8732ea6205ffdcd5eb3d03b1f7621eb3`, merged to `main` as
`cc03eb42a3bef67c4adb0dc1e7c2a421d4699868` (ordered parents
`65c5909d33a8` then the reviewed head; merge tree equal to the
reviewed feature-head tree). Exact-head PR CI run `30750293487` and
exact-merge push CI run `30750472801` both completed successfully —
five jobs green, zero artifacts, attempt 1 (the third and fourth
consecutive clean merge-CI e2e runs since the PR #44 keep-alive
correction).

**Boundary.** No migration, no new endpoint, no dependency change, no
`schema_version` bump. No browser-level hours coverage (M5E owns the
journeys and per-variant acceptance for the new section), no ordering
behavior (M6). The four retained risks stand unchanged.

### M5C close-out (2026-08-02)

M5C delivered the **hours workspace** at the blueprint-reserved
`/businesses/:businessId/hours` route, entirely inside
`apps/control-center` (no backend, contract, schema, generated-client,
or dependency change). The weekly editor speaks the D1 minute encoding
through time inputs plus an explicit "closes next day" choice; saves
are full-document and explicit with exact-payload semantics and dirty
tracking; client-side same-day overlap and encoding validation blocks
Save but never typing, and the server's 422s are surfaced where they
were caused (the exception window renders its bounds inside the
dialog). **Spring-forward gaps are flagged where they are authored**:
an Intl round-trip detects a nonexistent wall time on its actual
upcoming occurrence date and warns non-blockingly, stating the server's
gap-end rule — the silent-shift failure mode this milestone exists to
prevent, made visible at authoring time. Exceptions are edited per date
(special hours, or closed-all-day with the D6 note) and removed through
the confirm pattern; the fulfillment form presents the registry
defaults honestly (`is_configured`) before the first write
materializes them. **Ruling D7 is visible in navigation**: Hours is
offered to every role — staff read the schedule they work with no
mutating controls, owners and managers edit, and a closed business
stays readable while every mutation is withheld.

**Verification.** Control-center **478** (from 439; +39 covering the
pure time helpers including Intl gap detection across New York and
Phoenix and the fall-back fold, the role-by-lifecycle matrix, exact
weekly/exception/fulfillment payloads including the next-day encoding,
the in-dialog window 422, and the DST warning under a frozen clock);
every other suite unchanged; the full gate green including the
23-test browser suite.

Merge evidence (PR #46): reviewed feature head
`27360dc101f9f2131c21471044f0a83aa1019a8c`, merged to `main` as
`d682080cb6c25bd80c609a1e4500fbb61722a680` (ordered parents
`1a7ee053805e` then the reviewed head; merge tree equal to the
reviewed feature-head tree). Exact-head PR CI run `30734340536` and
exact-merge push CI run `30734468224` both completed successfully —
five jobs green, zero artifacts, attempt 1 (the first two merge-CI
e2e runs since the PR #44 keep-alive correction, both clean).

**Boundary.** No `hours` storefront section or renderer change (M5D),
no browser-level hours coverage (M5E), no ordering behavior (M6).

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
