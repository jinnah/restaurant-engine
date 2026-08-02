# ADR-025: Hours, exceptions, and fulfillment settings (Milestone 5)

- **Status:** Accepted — delivered in full: M5A (2026-08-01), M5B–M5E (2026-08-02); Milestone 5 complete
- **Date:** 2026-08-01
- **Deciders:** Jinnah (product owner / principal architect), Claude (senior engineer)

## Context

Milestone 5 is the blueprint §19 commitment: weekly hours, exceptions,
fulfillment settings, a pickup-slot service, hours UI, and storefront
display, with exit criteria that DST, closure, lead-time, and next-opening
tests pass and public availability derives from structured settings.
Blueprint §7.6 fixes the ground rules — hours are structured local time
plus the tenant timezone, never freeform storefront text; instants are
computed carefully across daylight-saving transitions; the domain answers
"what is the next valid pickup time?" — and §9 names the tables:
`business_hours`, `schedule_exceptions`, `fulfillment_settings`.

The delivered codebase has been holding M5's seams open deliberately:

- the section registry (M4A) excludes any hours or "open now" field and
  names M5 as the owner; `ContactProps` carries "deliberately no hours
  field of any kind";
- `businesses.timezone` exists, is validated against
  `zoneinfo.available_timezones()` at creation, and already reaches every
  public projection through `PublicSiteSummary` — but is writable only at
  creation, with no correction path;
- the public cache policy (M4C) grants caching by route identity, so a
  new public route defaults to `no-store` unless deliberately granted;
- the blueprint reserves `GET /api/v1/public/availability` (§10.1) and
  the control-center route `/businesses/:businessId/hours` (§13).

M5 does not include ordering, cart, or checkout (M6), order operations
(M7), or anything in M8–M11. The ADR-024 §13 non-goals stand.

## Decision

Milestone 5 is delivered as a new `hours` domain
(`backend/app/domains/hours/`) owning the three §9 tables, a pure
timekeeping-and-availability core with an injected clock, a business-scoped
administrative API, a host-resolved public availability projection, hours
administration in the control center, and an `hours` storefront section —
in five separately authorized slices (§12), under the rulings below (§11).

### Domain boundaries

`hours` depends on `businesses` for the tenant timezone and the lifecycle
preamble, exactly as catalog and storefront do. The storefront domain does
not import hours: the `hours` _section_ carries presentation choices only,
and the hours _data_ is composed at render time by the storefront
application, the same way the menu section composes with the public menu
projection. Orders (M6) will consume the pickup-slot service through an
explicit interface; M5 does not anticipate its call sites.

The timekeeping and availability modules are **pure**: no database, no
ambient clock — `now` is always an argument. That is what makes the DST
exit criteria exhaustively and deterministically testable, and it is the
single most important structural decision in this milestone.

### Data model

**`business_hours`** — the recurring weekly schedule. One row per interval:
`day_of_week` (0–6, Monday = 0, ISO 8601), `opens_minute` (0–1439, minutes
from local midnight), `closes_minute` (1–2879, where a value above 1440
means the interval ends on the following local day). Multiple intervals per
day are supported from the start (split lunch/dinner service is ordinary
for restaurants; retrofitting later would migrate live tenant data).
Non-overlap within the week is validated as a pure function of the
submitted full-week set before any write; a PostgreSQL `EXCLUDE` backstop
would require the `btree_gist` extension and is recorded as a hardening
candidate, not adopted.

**`schedule_exceptions`** — date-specific overrides. Any exception row for
a local calendar date **fully replaces** the weekly schedule for that date.
A single row with a NULL interval means closed all day (a partial unique
index allows at most one such row per date); one or more interval rows are
that date's special hours. An optional bounded plain-text `note` explains
the exception (D6). Writes are accepted only inside a bounded window
(30 days back, 550 days forward, in the tenant's local calendar); past
exceptions are retained as history.

**`fulfillment_settings`** — at most one row per business:
`pickup_enabled`, `asap_enabled`, `lead_time_minutes`,
`slot_interval_minutes`, `last_order_before_close_minutes`,
`max_days_ahead`. **No row means the documented defaults**, projected on
read and materialized on first write — the M4G-A compatibility mechanism,
avoiding any backfill.

All three tables carry `business_id` first in every index (§8.2 of the
blueprint). Concurrency is the Business `FOR UPDATE` row lock, consistent
with catalog; hours are low-conflict, so no optimistic-concurrency token.

### Timekeeping rules (the DST contract)

1. Storage is local wall-clock time only — weekday plus minute-of-day, or
   local date plus minute-of-day. No UTC offset is ever stored: offsets
   change, and a stored offset silently rots.
2. The tenant's IANA timezone is the only bridge, resolved through
   `zoneinfo` at computation time so tzdata updates are picked up.
3. **Spring-forward gaps:** a local time inside the gap does not exist;
   `zoneinfo` does not raise — it silently shifts. The rule is explicit:
   nonexistence is detected (the two fold conversions disagree with the
   gap ordering) and the boundary moves **forward to the end of the gap**
   — the transition instant itself. A 02:30 opening on the spring-forward
   date opens at 03:00 local.
4. **Fall-back ambiguity:** a local time inside the repeated hour occurs
   twice. **Opening** boundaries take the earlier occurrence (`fold=0`);
   **closing** boundaries take the later (`fold=1`). The open window is
   the union — a business advertising 01:00–02:00 is open the whole
   repeated hour. The closing rule must be written explicitly, because
   `fold=0` is Python's default and the omission would be silently wrong.
5. Overnight intervals are converted **end-to-end** — each boundary
   independently from (local date, minute) to an instant — never as
   start-plus-duration, so an interval spanning a transition has the
   correct real-world length. An interval entirely inside a gap collapses
   (closes ≤ opens) and contributes nothing.
6. "Today" is the tenant's local date derived from the injected `now` and
   the tenant zone — never the server's date, never UTC's date.
7. Order timestamps in UTC plus the retained tenant timezone (§7.6) are
   M6's obligation; M5 records the rule and does not implement it.

### Availability and the pickup-slot service

One pure computation: given the weekly schedule, the exceptions, the
fulfillment policy, the timezone, and `now`, produce `is_open_now`,
`closes_at` (when open), `next_opens_at` (when closed), `next_pickup_at`,
and bounded slot enumeration. Precedence is fixed: resolve the tenant-local
date; an exception replaces that date's weekly schedule entirely; intervals
become instants under the rules above; openness is instant containment.
An overnight interval belongs to the local date whose schedule created it —
Monday 17:00–02:00 still runs to 2 a.m. Tuesday even when Tuesday carries a
closed-all-day exception, because it is Monday's service. Pickup slots step
in real time (`slot_interval_minutes`) from each interval's opening, are
valid from `now + lead_time_minutes` through
`closes_at − last_order_before_close_minutes`, and are bounded by
`max_days_ahead` counted in **service days** (the local date whose schedule
created the interval). The next-opening scan is bounded (400 days), so a
business with no hours terminates with "none" rather than looping.

The pickup-slot service ships without a consumer: M6's checkout is its
real proving ground, and building it beside the hours it depends on is far
cheaper than bolting it on during checkout. The close-out must say this
plainly.

### API surface

Administrative (business-scoped; the established preamble — membership
capability, Business `FOR UPDATE`, lifecycle gate; closed businesses stay
readable and refuse mutations with 409 `invalid_state`):

- `GET  /businesses/{id}/hours` — the complete operating configuration in
  one read (timezone, weekly schedule, exceptions in the bounded window,
  effective fulfillment settings);
- `PUT  /businesses/{id}/hours/weekly` — full-week replacement (the
  full-document precedent of the storefront draft and the entitlement
  set): overlap validation is a pure function of the submitted set, the
  command is idempotent, and the exact no-op is suppressed;
- `PUT  /businesses/{id}/hours/exceptions/{date}` /
  `DELETE /businesses/{id}/hours/exceptions/{date}` — per-date upsert and
  removal (the date is the natural idempotency unit; a full-set PUT would
  make an eighteen-month schedule one hostile payload);
- `PUT  /businesses/{id}/hours/fulfillment` — full-document settings;
- `GET  /businesses/{id}/hours/preview?at=` — an authenticated probe
  answering "what would a customer see at this instant", so an owner can
  check a DST weekend or a holiday before it happens and the E2E suite can
  exercise transitions deterministically.

Platform: `PUT /platform/businesses/{id}/timezone` (D2) — the first
correction path for a creation-time tenancy fact, audited, platform-only.

Public (M5B): `GET /api/v1/public/availability` — host-resolved, active
businesses only, neutral 404 for every other cause (ADR-013), `no-store`
(D4). Hours are deliberately **not** embedded in the published storefront
projection: that projection is an immutable snapshot of a published
version, cached for 60 seconds, and hours are live operational data that
must never be frozen into a version, archived with it, or restored from
it.

Capabilities: one new — `business.hours.write` (owner and manager, per
blueprint §7.1's manager role). Hours reads ride on `business.view` (D7).
The timezone command rides on `platform.businesses.manage`.

Audit actions: `business.hours_updated`,
`business.schedule_exception_set`, `business.schedule_exception_removed`,
`business.fulfillment_updated`, `business.timezone_changed` — typed detail
schemas, bounded values, no free text (an exception note never enters an
audit payload).

### Storefront display (M5D)

A registered `hours` section type, following `MenuProps` exactly: its
props carry a heading, an optional intro, and whether to show live
open/closed status — and **no hours data whatsoever**. The schedule
arrives at render time from the availability projection. Per the M4G-B
ruling, the registry entry, all three variant renderer arms, and the
composer control land in one slice, so the enum and the renderer cannot
drift apart. The Restaurant JSON-LD gains `openingHoursSpecification`
through the existing audited serializer (§12.2: hours are modeled, not
embedded in decorative text). The storefront home route grows from two
backend requests to three; the built-server verification's exact-cost
assertion is updated in the same slice, visibly.

## Rulings

- **D1 — Interval encoding.** Integer minutes from local midnight;
  `closes_minute` above 1440 means the following local day. One
  CHECK-enforceable value for the overnight case; a `TIME` plus an
  overnight flag is two representations that can disagree. Cost:
  readability in raw SQL.
- **D2 — Timezone correction.** M5 adds the platform-only, audited
  timezone-change command. Every hours computation is a function of
  `businesses.timezone`, and a business onboarded into the wrong zone
  would be systematically wrong with no repair path short of direct SQL.
  Timezone is a tenancy-level fact like the slug — platform-assigned,
  never tenant content. The sibling gap (no business rename surface)
  stays out of M5: a name is display text and does not threaten
  correctness.
- **D3 — Throttling deferred.** Blueprint §7.6 names order throttling;
  it means counting orders per slot, and orders do not exist until M6.
  Storing a setting M5 cannot enforce is a placeholder for
  later-milestone behavior, which the project prompt forbids.
- **D4 — No public cache grant.** The availability response is
  time-derived by construction; a 60-second grant would make "Open now"
  wrong for up to a minute at exactly the boundaries a customer checks.
  `cache_control.py` is unchanged.
- **D5 — Hours as a section, data-free.** The `hours` section carries
  presentation choices only; the projection supplies the data. Storing
  hours in the section would create a second source of truth and freeze
  schedules into published history.
- **D6 — Exception notes.** An optional customer-visible note, bounded
  plain text through the domain's normalize/control-character policy. A
  label on structured data is not the freeform hours text §7.6 forbids —
  the hours themselves stay machine-readable.
- **D7 — Read capability.** Hours reads ride on `business.view`; staff
  see the schedule they work. Only the write capability is new.

## Alternatives considered

- **`TIME` columns with an overnight flag** — rejected (D1): two
  representations of one fact, and the overnight case becomes
  unexpressible in a single CHECK.
- **Embedding hours in the published storefront projection** — rejected:
  it would freeze live operational data into immutable versions, restore
  stale hours from archives, and inherit a cache lifetime chosen for
  published content.
- **A per-interval CRUD API** — rejected in favor of full-week
  replacement: overlap validation becomes a cross-request problem, and
  the reorder/entitlement precedents show the full-set command is the
  idempotent, race-free shape.
- **`EXCLUDE USING gist` non-overlap backstop** — deferred: it requires
  the `btree_gist` extension (a deployment decision) for a race the
  Business row lock already serializes. Recorded as a hardening
  candidate.
- **Caching the availability response briefly** — rejected (D4).
- **Deferring the timezone command to a future business-settings
  milestone** — rejected (D2): M5 makes the column load-bearing, so M5
  owns the repair path.

## Consequences

Easier: M6 checkout consumes a proven pickup-slot service; the storefront
gains an "open now" answer derived from structured data; the platform can
finally correct a mis-onboarded timezone. Harder: the storefront home
route costs a third backend request (measured and asserted); the hours
domain adds a second clock-sensitive test discipline (the injected-`now`
convention must be maintained); tzdata provenance becomes a runtime
dependency worth pinning explicitly (Windows has no system database, so
the backend relies on the `tzdata` package).

New obligations: M6 must implement throttling (D3) and the UTC-plus-
tenant-timezone order timestamp rule; the M5E close-out must state
plainly that the slot service is proven by unit tests and the public
`next_pickup_at`, not by a real checkout.

## Security and operations impact

No new authentication surface. The public availability endpoint is
host-resolved with the established neutral-404 semantics and discloses
nothing an open restaurant's door does not. Tenant isolation follows the
standing matrix: every table is tenant-leading, every repository method
requires `business_id`, and the §8.5 matrix extends to the three new
resources. The timezone command is account-of-record data with audit
trail; it changes how stored local times are interpreted, which is
exactly why it is platform-only and audited. No new dependency, no new
infrastructure, no cache grant, no change to session, CSRF, or media
behavior.

## Delivery slices (§12)

| Slice                             | Scope                                                                                                                                                             | Depends on |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **M5A** — Hours domain foundation | tables + migration, pure timekeeping/availability with the exhaustive DST suite, admin API, D2 timezone command, capability, audit actions, contract regeneration | —          |
| **M5B** — Public availability     | `GET /api/v1/public/availability`, neutral failure semantics, isolation tests                                                                                     | M5A        |
| **M5C** — Hours workspace UI      | `/businesses/:id/hours`: weekly editor (with DST-gap warning), exceptions, fulfillment settings                                                                   | M5A        |
| **M5D** — Storefront display      | `hours` section + three renderer arms + composer control (one slice), JSON-LD hours, updated request-cost assertion                                               | M5A, M5B   |
| **M5E** — E2E and close-out       | journeys, per-variant acceptance for the new section, documentation, exit-criteria verification                                                                   | all        |

Each slice is separately authorized and reviewed, one PR each, with the
standing verification gates.

## Reconsideration triggers

- M6 discovers the slot service's shape does not fit checkout (e.g.
  per-slot capacity requires a different enumeration contract).
- A tenant needs more than four intervals per day, or exceptions beyond
  the 550-day window.
- Evidence that per-request availability computation is a measurable cost
  (would reopen D4 with a short-TTL or validator-based design).
- A second consumer needs hours data inside the published projection
  (would reopen the separate-endpoint decision).
- Adoption of `btree_gist` elsewhere (would make the EXCLUDE backstop
  cheap to add).

---

## Delivery record

### M5A — Hours domain foundation: delivered, 2026-08-01

Delivered exactly the §12 M5A scope: the three tables on migration
`c3d8f5a21e47` (from `a41d9c7e5b30`), the pure
`hours.timekeeping`/`hours.availability` core with the injected clock
and the §"Timekeeping rules" DST contract proven exhaustively (New York
gap and fold, Phoenix, Sydney, Lord Howe, overnight-across-transition,
bounded scans), the six-operation hours administration API with
full-set-replacement semantics and exact no-op suppression, the D2
platform timezone command, `business.hours.write` (D7: reads on
`business.view`), five audit actions with typed details and read-time
projections (the D6 note's content never recorded), and the regenerated
contract — **66 → 73 operations** — with the `hours` client facade
group and `platform.setTimezone`.

Verification: backend 1,228 (from 1,132), api-client 106 (from 95),
every other suite unchanged; ruff, strict mypy (193 files), workspace
lint/format/typecheck, `contract:check`, both builds, the storefront
budget/verification, and the 23-test Playwright suite all green. Merge
evidence: PR #41, reviewed head `dc156ed1`, SHA-bound merge
`0f46640a7548402a878bc7c2e4da134906740971` (parents `37ff016f` then the
reviewed head; merge tree equal to the reviewed head tree); exact-head
CI run `30730811615` and exact-merge push CI run `30730938069` both
green 5/5 with zero artifacts on attempt 1.

Deliberately not delivered (their own slices): the public availability
endpoint (M5B), the hours workspace UI (M5C), the `hours` storefront
section (M5D), browser-level acceptance (M5E), and order throttling
(D3 — M6). The pickup-slot service ships without a consumer; M6's
checkout is its first genuine exercise.

### M5B — Public availability: delivered, 2026-08-02

Delivered exactly the §12 M5B scope: `GET /api/v1/public/availability`
(plus a schema-hidden `HEAD` companion) — host-resolved, active
businesses only, one neutral 404 for every other cause, every active
business answering (an empty schedule is honestly closed, never a 404),
the projection derived from structured settings through the pure core,
exceptions bounded to a 60-day forward window, minimal pickup facts,
and **no cache grant** (ruling D4 upheld; `no-store` pinned on success
and failure). Contract **73 → 74**; the public facade gains
`getAvailability()`; `effective_policy()` shared between the member
preview and the public projection.

Verification: backend 1,240 (from 1,228), api-client 109 (from 106),
every other gate unchanged and green. Merge evidence: PR #43, reviewed
head `2bcd0899`, SHA-bound merge
`b9e21c66a7cd6cecbf9555e53d5a050048f12cca` (tree equal to the reviewed
head tree); exact-head CI run `30732083089` green 5/5, zero artifacts.
The exact-merge push run `30732209402` **failed twice** in the
pre-existing storefront-design-assignment isolation journey on a
connection-level SSR fetch failure (diagnosis and full record in
docs/08's M5B close-out); corrective PR #44 (merge `4836e693`, its
exact-head run `30732731236` and exact-merge run `30732874509` both
green 5/5) widened the orchestrated E2E backend's keep-alive window —
no assertion weakened, no production change. If the signature ever
reappears with the flag in place, the keep-alive reading is falsified
and the investigation must reopen.

### M5E — E2E and close-out: delivered, 2026-08-02

Delivered exactly the §12 M5E scope, entirely under `e2e/` (a test-only
change; no application, contract, schema, CI-workflow, or dependency
change). The Playwright suite grew 23 → **25**. The hours journey
drives the real product surfaces end to end: an owner authors the
all-day weekly schedule in the M5C weekly editor (the D1 next-day
choice) and a dated closed-all-day exception with a D6 note, composes
the hours section in the M5D composer — whose dialog provably offers
no schedule input — publishes, and an anonymous visitor on the tenant
host sees the schedule, the exception with its note, the live "Open
now" status, and the JSON-LD `openingHoursSpecification`. A second
spec pins the honestly-closed state: a published hours section over an
empty schedule renders "Closed now" with no fabricated next opening,
seven honest "Closed" rows, no special-hours block, and no JSON-LD
hours claim. Both are **time-robust by construction** (the trap this
ADR records): the server computes `is_open_now` from the real current
instant, so nothing overrides the browser clock — open-around-the-clock
and no-schedule are the two states whose status holds whenever and
wherever the suite runs, and instant-exact DST assertions stay in the
unit matrix, where the clock is injected. Per-variant acceptance now
covers the six-section page: the seeding fixture gained an opt-in
hours option (existing callers submit exactly the document they always
did), and the classic responsive matrix, the editorial/express
per-variant matrix, and both axe scans run over a live schedule, with
the M5C hours workspace added to the workspace scan.

**The pickup-slot service ships proven by its unit suite and the
public `next_pickup_at` — not by a real checkout.** No consumer exists
until M6's checkout, which is its genuine proving ground; this is the
plain statement the Consequences section required.

Verification: `pnpm e2e` 25 passed (Windows and the Linux CI runs
below); orchestrator regression 42 + 1 known Windows-symlink skip;
every other suite and gate unchanged and green (backend 1,245 exit 0
on the exact tree, contract byte-current at 74 operations, budgets
unmoved). Merge evidence: PR #50, reviewed head `ec39d8b6`, SHA-bound
merge `4d97eefefda4822821603ab4b885b57296b66fb9` (parents `032b0640`
then the reviewed head; merge tree `880bf978` equal to the reviewed
head tree); exact-head CI run `30752173747` and exact-merge push CI
run `30752361747` both green 5/5 with zero artifacts on attempt 1.

With M5E delivered, every §12 slice is complete and the blueprint §19
exit criteria are verified — the Milestone 5 close-out in docs/08 is
the completion record.

### M5D — Storefront display: delivered, 2026-08-02

Delivered exactly the §12 M5D scope, in one slice per the M4G-B ruling
(registry entry, renderer, and composer control together, so the enum
and the renderer cannot drift): the `hours` section type registered
with presentation choices only — heading, optional intro,
`show_open_now` — and **no schedule of any shape** (ruling D5 made
structural: the exact field set is pinned by test and every
schedule-shaped smuggling attempt is a 422); the public projection
carrying those choices verbatim; one shared `HoursSection` rendered
under all three variant arms (chrome only, no per-variant fork) from
pure D1-minute/instant formatting helpers with no ambient clock — the
open/closed answer is the server's, only formatted in the tenant
timezone — with an honest all-closed rendering of an empty schedule
and null-data degradation for the workspace preview (the MenuSection
precedent); the composer offering Hours with heading/intro/status
fields and no schedule input. The storefront home route grew from two
backend reads to **three**: the availability projection is read on
every home render, because the Restaurant JSON-LD now models
`openingHoursSpecification` (blueprint §12.2) independently of section
composition — the D1 overnight case uses schema.org's
closes-before-opens convention, a full 00:00–24:00 day is stated as
00:00–23:59, and an empty schedule claims nothing. The built-server
verification's exact-cost assertion moved to three in the same slice,
visibly; `/menu` stays at two. Upcoming exceptions render in the
section (with the D6 note as plain text) but are deliberately not
claimed in JSON-LD: transient overrides rot in a crawler's index.

Verification: backend 1,245 (from 1,240), storefront-renderer 161
(from 146), storefront 78 (from 70), control-center 480 (from 478),
api-client 109 unchanged; contract regenerated with **74 operations
unchanged** (new component schemas only) and byte-current; zero client
JavaScript added (first-load budget unmoved at 456,547 B); every other
gate green including `pnpm e2e` 23. Merge evidence: PR #48, reviewed
head `26e141ae`, SHA-bound merge
`cc03eb42a3bef67c4adb0dc1e7c2a421d4699868` (parents `65c5909d` then
the reviewed head; merge tree equal to the reviewed head tree);
exact-head CI run `30750293487` and exact-merge push CI run
`30750472801` both green 5/5 with zero artifacts on attempt 1.

Deliberately not delivered: browser-level hours coverage and
per-variant acceptance for the new section (M5E), and ordering
behavior (M6).

### M5C — Hours workspace UI: delivered, 2026-08-02

Delivered exactly the §12 M5C scope, entirely inside
`apps/control-center`: the hours workspace at the reserved
`/businesses/:businessId/hours` route — the D1 weekly editor with the
explicit next-day choice and full-document explicit saves, per-date
exception editing (special hours or closed-all-day with the D6 note)
with the editable-window 422 rendered in place, the fulfillment form
presenting the registry defaults honestly before first write, the
authored-time DST-gap warning (Intl round-trip naming the actual
upcoming gap date, non-blocking, stating the server's gap-end rule),
and ruling D7 visible in navigation (Hours offered to every role;
staff read-only; closed businesses readable and immutable).

Verification: control-center 478 (from 439); every other suite and
gate unchanged and green, including the 23-test browser suite. Merge
evidence: PR #46, reviewed head `27360dc1`, SHA-bound merge
`d682080cb6c25bd80c609a1e4500fbb61722a680` (tree equal to the reviewed
head tree); exact-head run `30734340536` and exact-merge run
`30734468224` both green 5/5, zero artifacts, attempt 1.
