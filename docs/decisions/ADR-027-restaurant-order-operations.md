# ADR-027: Restaurant order operations (Milestone 7)

- **Status:** Accepted — delivered in full (M7A–M7D, 2026-08-02/03); Milestone 7 complete
- **Date:** 2026-08-02
- **Deciders:** Jinnah (product owner / principal architect), Claude (senior engineer)

Prepared against `main` @ `c662d8e4` (Milestone 6 complete), reviewed
2026-08-02 with four amendments recorded inline (D1's refusal carries
the current status in typed details, not a body representation; D7's
timeline is the status-event trail alone; D8 gains precise computed
expiry semantics; D8's write path is its own command rather than a
fulfillment-document field — the full-document PUT would have let the
delivered M6D panel silently unpause a business between slices).
Authority: blueprint §7.7, §13, §14.3, §15.3 (journey 5), §19 (M7);
docs/08's strengthened 2026-07-23 active-restaurant commitments;
ADR-026's delivered order store.

---

## 1. Context — what M7 inherits, verified in the delivered code

- The order store is proven: five tenant-leading tables;
  `orders.status` already carries the complete §7.7 enum
  (`M6_PRODUCIBLE_STATUSES` was written to move in M7);
  `order_status_events` is append-only with a never-written `member`
  actor arm; orders use UUIDv7 ids — time-ordered by construction, so
  an id cursor is a time cursor.
- The customer tracker (M6C) already renders all seven statuses, polls
  at 15 s, and stops on terminal states: the §19 criterion "customer
  tracker reflects transitions" needs zero customer-side code beyond
  the D7 estimate line.
- Concurrency machinery exists: the Business `FOR UPDATE` pattern
  (placement, D11 customer cancel). Discovery found one gap:
  `count_orders_for_slot` excluded only `cancelled` — a rejected order
  still occupied its pickup slot (fixed by D3).
- The capability registry is append-only with the staff-reachable
  precedent (`business.catalog.availability`); audit actions are enum +
  typed details + read projection; the CC reserves the orders nav slot
  and has no polling consumer yet — M7 is §14.3's first.
- The 2026-07-23 commitments widen the milestone beyond the blueprint
  baseline: prep estimates, pause/resume with a customer-visible
  explanation, dashboard metrics, print tickets, search and history.
  Payment status and order source hold exactly one value each today —
  display constants, not columns.

## 2. Decision summary

Milestone 7 delivers the member half of the order lifecycle: five
guarded transition commands plus a member cancellation, an operational
list/detail/timeline read surface with filters and cursor pagination, a
prep-estimate command the tracker reflects, the ordering pause/resume
vertical (hours-owned state, its own command, customer-visible
storefront presentation), the live order board in the control center
(polling, user-controlled new-order alert, operational-language status
columns, order age and overdue indicators, print-friendly ticket,
metrics strip), and the e2e closure (journey 5 plus a deterministic
concurrency proof). One additive migration (`b3e1f0a7c254`):
`orders.estimated_ready_at`, the three pause fields on
`fulfillment_settings`, and the `(business_id, id)` list index. No new
tables, no new dependencies.

## 3. Rulings (D1–D12, as amended in review)

- **D1 — Transitions are named commands validating the machine inside a
  locked transaction.** `accept`/`reject` from `submitted`;
  `start-preparing` from `accepted`; `mark-ready` from `preparing`;
  `complete` from `ready`. The command locks the order row
  (`SELECT … FOR UPDATE`), re-reads the state, and refuses anything
  illegal with `409 invalid_state` whose typed details carry the
  current status — the losing device of a race refetches and shows the
  truth; state cannot corrupt (§19). Each command appends the status
  event (`actor_kind = member`, `actor_user_id` set) and audits, in one
  transaction.
- **D2 — One new capability, `business.orders.operate`**, granted to
  owner, manager, AND staff (§7.1). It gates the reads and the
  commands: the operational surface carries customer PII, so its
  authority is named, never inherited from `business.view`. Platform
  admins hold no membership → 404, as everywhere.
- **D3 — Rejection and member cancellation release the pickup slot.**
  `count_orders_for_slot` excludes `rejected` alongside `cancelled` (a
  refused order occupies no kitchen capacity). `reject` and the member
  `cancel` therefore run under the **Business lock** (the D11-M6
  precedent: slot release serializes with placement counting); the pure
  forward transitions take only the order-row lock. Lock ordering is
  acyclic: Business → order for the releasing commands, order alone for
  the rest, Business alone for placement.
- **D4 — Member cancellation is legal only from `submitted`** — the
  §7.7 machine's one path to `cancelled`, now walkable by a member (the
  phoned "please cancel" case), evented and audited as
  `order.cancelled_by_member`. The machine grows no edges in M7;
  pilot evidence reopens that as a blueprint amendment.
- **D5 — No free-text rejection reason.** No storage exists, and a
  reason is customer communication — it belongs to the notification
  channels. The tracker keeps saying "Declined by the restaurant".
- **D6 — The operational read surface.** List: exclusive UUIDv7-id
  cursor (the ADR-014 audit precedent), descending, bounded page size,
  filters `status`, `placed_after`/`placed_before`, and one bounded `q`
  matching the order number exactly or customer name/phone/email by
  prefix — which is also "customer-linked order history" (the same
  list, filtered by the customer's contact). Detail: the full
  operational projection — customer name/phone/email, item and order
  instructions, consents, snapshot lines, promise, estimate, and the
  complete status-event timeline. PII on this surface is the point (the
  counter calls the customer by name); audit details stay PII-free.
- **D7 — The estimate command.** `PUT …/orders/{id}/estimate` sets or
  clears `estimated_ready_at`, legal while the order is `accepted` or
  `preparing`. The estimate is not a status: the timeline stays the
  status-event trail alone (review amendment), the change is audited
  (`order.estimate_set`), and the detail shows the current value.
  `PublicOrderView` gains the field; the tracker renders it when
  present (M7B).
- **D8 — Pause/resume is hours-owned state with its own command,
  orders-enforced, customer-visible.** Storage on
  `fulfillment_settings`; the write path is
  `PUT /businesses/{id}/hours/pause` (owner/manager via
  `business.hours.write`) — deliberately NOT a fulfillment-document
  field, so the delivered M6D panel cannot silently unpause a business
  (review amendment). Effectiveness is computed, never scheduled:
  `paused AND (resume_at IS NULL OR now < resume_at)`; an expired pause
  reads as resumed and the workspace shows it honestly. Placement
  refuses while effectively paused with a typed `409 ordering_paused` —
  deliberately not the neutral 404: D10-M6 hides capabilities that do
  not exist; pause is a capability that exists and is honestly,
  temporarily off. The public availability projection carries the
  effective pause facts (flag, note, resume instant);
  `ordering_enabled` itself is unchanged. The storefront (M7B) renders
  the paused `/order` explanation; cart-building stays alive — a
  temporary pause must not destroy half-built carts.
- **D9 — The board polls; nothing pushes.** TanStack `refetchInterval`
  ~10 s, no background-tab refetch, §14.3 verbatim. The tracker keeps
  its 15 s. SSE remains a post-measurement option.
- **D10 — The new-order alert is client-side and user-controlled.**
  Poll-diff detection → prominent visual alert always; the chime is
  behind an explicit toggle, off by default, persisted per device.
- **D11 — Metrics are reads, not storage.** Today-in-tenant-zone order
  count, sales (non-rejected/non-cancelled totals), average order
  value, cancellation+rejection rate, popular items (snapshot lines),
  and prep-time performance (ready minus accepted event instants) —
  straight SQL over the delivered tables.
- **D12 — The ticket is print CSS, not a document pipeline.**

## 4. Delivery slices (each separately authorized, one PR each)

| Slice                              | Scope                                                                                                                                                                                                                                                           | Depends on |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **M7A** — Order operations backend | migration, capability, five transition commands + member cancel (D1–D5), estimate command (D7), list/detail/timeline/metrics reads (D6, D11), slot release on reject (D3), pause command + enforcement + public pause facts (D8), audit actions, contract regen | —          |
| **M7B** — Storefront pause state   | the paused `/order` presentation, availability-projection consumption, the tracker estimate line                                                                                                                                                                | M7A        |
| **M7C** — The order board          | board, drawer, timeline, guarded actions, estimate control, search/filters, metrics strip, chime + toggle, print ticket, pause control + hours-page display                                                                                                     | M7A        |
| **M7D** — E2E and close-out        | journey 5 (staff accept → prepare → ready; the visitor's tracker reflects each transition), the API-level concurrency race proof, board responsive/a11y acceptance, docs close-out and §19 exit-criteria verification                                           | all        |

## 5. What M7 deliberately does not do

No refunds (post-pilot, with payments). No customer notifications — the
channels and the outbox worker (ADR-026 D14) stay deferred; the tracker
is the notification. No SSE/WebSockets. No per-IP rate limiting (M8).
No rejection reasons (D5). No printing pipeline (D12). No new
storefront dependency or budget change.

## 6. Reconsideration triggers

- Measured board latency or polling load → SSE (§14.3's own trigger).
- A notification channel lands → D5 reopens; the outbox worker ships.
- Online payments land → payment status becomes data; refunds enter.
- Pilot evidence of post-acceptance cancellation need → a §7.7 machine
  amendment (D4's recorded boundary).
- Multi-station kitchens → the ticket view grows into a real KDS
  decision.

---

## Delivery record

### M7A — The order operations backend: delivered, 2026-08-02

Delivered exactly the §4 M7A scope, with two delivery corrections
recorded as amendments:

- **D6 as amended in delivery — the cursor is the order number.** The
  ADR (and the discovery it came from) assumed UUIDv7 order ids from
  ADR-026 §3's data model; the delivered placement generates **random
  UUID4** ids, so an id cursor would not be a time cursor. The list
  pages newest-first behind an exclusive cursor on the dense,
  tenant-scoped `order_number` — monotonic by construction (allocated
  under the Business lock) and served by the existing
  `(business_id, order_number)` unique, so the planned `(business_id,
id)` index was dropped from the migration before it shipped.
- **D3's lock discipline proven end-to-end:** the slot count excludes
  `rejected` alongside `cancelled`; reject and member-cancel take the
  Business lock before the order-row lock; a test fills a
  one-order slot, watches a second placement refuse, rejects the
  first, and watches the same placement succeed.

The six named member commands (D1/D4) validate the current state under
the locked order row, append the member-actor status event, and audit —
`409 invalid_state` carries the current status in typed details. The
D2 capability `business.orders.operate` gates reads and commands for
owner, manager, and staff; platform admins hold no membership and 404.
The estimate (D7) is its own PUT, legal in accepted/preparing, audited
set/cleared with exact no-op suppression, and rides `PublicOrderView`
(the tracker round-trip is proven by test). Pause/resume (D8) is its
own command on hours-write authority; effective pause is computed;
placement refuses with the typed `409 ordering_paused` carrying the
customer-visible note and resume instant, checked **after** the
idempotency replay lookup so a pre-pause order's honest retry still
reads; the public availability projection carries the effective facts
and an expired pause reads as resumed. Metrics (D11) are computed
today-in-tenant-zone reads.

One additive migration (`b3e1f0a7c254`): `orders.estimated_ready_at`
plus the three pause fields, server-defaulted unpaused. Nine new audit
actions with typed details and read-time projections (the six
transitions share one transition shape; the pause detail records note
PRESENCE, never its text). Contract **78 → 89**; the api-client gains
the `orders` facade group and `hours.setOrderingPause`; the CC mock
client and fulfillment fixtures grow the same seams so the M7C board
finds them ready.

Verification: backend **1,317** (from 1,301 — the transition matrix
including the race-shaped duplicate command; slot release against a
real racing placement; the authority matrix across all three roles,
the platform-admin 404, and cross-tenant nonexistence; cursor paging,
filters, and search; the estimate lifecycle including the tracker
round-trip; the pause vertical including expired auto-resume,
replay-during-pause, schema coherence, and staff refusal); api-client
115, renderer 165, storefront 143, control-center 483 unchanged and
green (fixture seams only); contract byte-current; builds, budget,
CSS, and built-server verification green; `pnpm e2e` 29 green with
full disposable cleanup.
Merge evidence: PR #60, reviewed head
`03c1d8135d143db5f26b271341c9e4a97ee5ab2f`, SHA-bound merge
`5f1c9a94244072485796ba96e8acb208da4d1d04` (parents `c662d8e4` then
the reviewed head; merge tree `f685a763` equal to the reviewed head
tree); exact-head CI run `30779327478` and exact-merge push CI run
`30779525969` both green — five jobs, zero artifacts, attempt 1.

Deliberately not delivered (their own slices): the storefront pause
presentation and the tracker estimate line (M7B); the order board
(M7C); the operations e2e journeys and close-out (M7D).

### M7B — The storefront pause state and the tracker estimate: delivered, 2026-08-03

Delivered exactly the §4 M7B scope — the customer half of what M7A
stored, all presentation, no contract or backend change.

The paused `/order` page (D8) renders the honest explanation instead
of the checkout form when the availability projection says ordering is
effectively paused: the owner's customer-visible note, the optional
"back around {instant}" formatted in the tenant zone, and the promise
that the saved cart survives — which it structurally does, because
localStorage is never touched. The notice is a **server component**
(nothing to hydrate), so the `'use client'` allowlist is unchanged.
The D10 gate is untouched: pause is a different state from
nonexistence. A pause that begins mid-checkout renders through the
island's new `ordering_paused` state, which deliberately **keeps** the
held idempotency key — retrying the same command after the resume is
an honest replay, never a duplicate. The tracker renders "Estimated
ready: {instant}" whenever the kitchen has set one (D7), arriving
through the polling it already does.

Verification: storefront **146** (from 143 — the paused page with note
and resume and no checkout island; the mid-checkout 409 keeping the
cart; the tracker estimate line); every other suite unchanged and
green; the built-server availability fixture gains the pause fields;
budget green (the checkout island grew 463 B, reported); `pnpm e2e`
29 green.
Merge evidence: PR #62, reviewed head
`31cef9eb7e653d19f82f7e903a025b8e50b1ffb1`, SHA-bound merge
`900dd186a1aac8a52a77ddc5a4b0d5f55493a1b5` (parents `05c50de1` then
the reviewed head; merge tree `b8e4a7f0` equal to the reviewed head
tree); exact-head CI run `30780730281` and exact-merge push CI run
`30780976212` both green — five jobs, zero artifacts, attempt 1.

Deliberately not delivered (their own slices): the order board (M7C);
the operations e2e journeys and close-out (M7D).

### M7C — The live order board: delivered, 2026-08-03

Delivered the §4 M7C scope — the control center's operational surface —
with three contract additions recorded below as delivery notes.

**The board (D6/D9/D11).** Status chips carry the docs/08 operational
vocabulary and never a wire value; the type of the label map is the
generated `OrderStatus` union, so a status added to the machine fails
the build here rather than showing "submitted" to a counter. The board
is deliberately undated by default — an order placed before midnight
and still preparing is still this shift's work — and polls at the D9
cadence, the §14.3 doctrine's first consumer. Search is bounded, sends
no status filter (an order somebody asks about by name is rarely still
"New") and says so on screen; that same query is D6's customer-linked
order history. The date filter is a tenant calendar day. A full page
offers "Load older orders" behind the D6 exclusive cursor, so history
is never a silently truncated first page. Tickets show number,
customer, age, the promise — or the kitchen's own estimate, labelled as
such — an overdue mark while work is still owed, and the total.
Metrics (D11) print in the currency the metrics carry.

**New orders (D10).** The alert rides a watch query that is
independent of every filter: an order arriving while staff read the
Ready column or yesterday's history still shouts, and the same query is
the honest source of the New count. The alert lives in a live region
that is always mounted (an arrival is an announced update, not a region
materializing), and its action takes the reader to the new orders. The
chime stays an explicit per-device opt-in, off by default, played
through the Web Audio API on the gesture that enabled it.

**The drawer (D6/D1/D4/D7/D12).** The full counter projection — the
PII this surface exists for, both instruction fields, consents, the
display constants, the snapshot lines — and the append-only timeline.
It offers exactly the legal commands for the current status and
nothing else; a raced `409 invalid_state` says the order changed on
another device and refetches rather than guessing. A consequential
refusal confirms **inside** the drawer: the control center keeps one
dialog open at a time, and nesting would have put two focus traps and
two elements carrying the same title id on the page. The estimate is a
duration ("20 min"), never a wall-clock picker — the device's timezone
is not necessarily the restaurant's — and the D12 ticket is print CSS.

**Pause/resume (D8)** sits on the board for owner and manager, with a
customer-visible note and a duration rather than an instant; the hours
panel displays the state read-only and points at the board.

**Three delivery notes — contract additions the board's real work
required, each additive and backward compatible:**

1. **`AdminOrderLine.item_instructions`.** The counter must read what
   the shareable public projection deliberately omits, so the admin
   detail's lines are their own schema extending the public line.
2. **`OrderMetrics.currency`.** Money needs its unit (blueprint
   §10.4). Without it the strip had to infer the currency from the
   first row — and a quiet morning has no row.
3. **The list `day` filter.** A tenant-local calendar date resolved
   server-side against the business timezone, because zone boundaries
   and DST transitions are the server's arithmetic (blueprint §7.6),
   not a browser's. It narrows an explicit instant window rather than
   replacing it. Metrics now share the same window helper, which
   retires a "midnight plus 24 hours" that would have leaked an hour
   across a transition.

Verification: backend **1,319** (from 1,317 — the zone-day filter
including the spring-forward boundary, and its intersection with an
explicit window); control-center **513** (from 483 — the board's
filters, search, day, cursor, overdue, metrics, alert and chime, empty
copy and pause control; the drawer's projection, legal-command matrix,
raced 409, estimate durations and print ticket; and the pure format
helpers at frozen times); api-client 115, renderer 165, storefront 146
unchanged and green; contract byte-current at 89 operations; ruff,
format, mypy, typecheck, lint, prettier, builds, budget (unchanged —
the storefront is untouched), CSS, and built-server verification green;
`pnpm e2e` 29 green.

Retained risk 1 recurred on the exact-head run's first attempt — the
M4E-era `storefront-dialogs-a11y` dirty-navigation test, the same
assertion as run `30652179044` — and passed on the re-run. It is not
M7C's: that test navigates programmatically, so the workspace's new
Orders link cannot reach it. The register keeps the risk open with a
second data point.

Deliberately not delivered (M7D): blueprint journey 5, the API-level
concurrency race proof, the board's responsive/a11y acceptance, and
the §19 exit-criteria close-out.

### M7D — The operations journeys and the acceptance: delivered, 2026-08-03

Delivered the §4 M7D scope — the proof, at the layer where each proof
is honest, that Milestone 7 does what §19 requires — plus two
accessibility corrections the acceptance work itself found in the
delivered board.

**The concurrency proof (§19: "two staff actions cannot corrupt
state").** Deterministic, not a sleep. Transaction A takes the order
row the D1 commands take and accepts the order itself; the production
accept command then runs in a second session and is observed **waiting
on that lock** in `pg_stat_activity` before A commits, so the overlap
is real rather than assumed. When A releases, B re-reads the row it now
owns, finds a state its transition is illegal from, and refuses with
`409 invalid_state` carrying `{"status": "accepted"}` — the truth the
losing device renders. The order keeps exactly one status event (the
customer's placement), gains no member event, and writes no transition
audit.

**Blueprint §15.3 journey 5.** Staff accept → prepare → ready in a real
browser while an anonymous visitor watches the tracker. The operator is
a genuine `staff` membership invited by the business's own owner
through the M2D business-scoped invitation, so ruling D2 is exercised
through a browser for the first time — and the same session is shown
holding no storefront section at all (ADR-020 §7), which is the other
half of that boundary. The visitor's page is **never reloaded**: each
transition is asserted by waiting for the poll the tracker already
does, because "the customer tracker reflects transitions" is a claim
about the customer's live page, not about the read endpoint. The D7
estimate crosses the same way — a duration on the board, an instant on
the tracker — and the drawer's timeline is checked for one member-actor
event per staff action, the arm ADR-026 left unwritten.

**The board's responsive and accessibility acceptance.** axe A/AA at
the ADR-023 rule boundary (zero violations, no exclusions) over the
board, the open drawer, its in-drawer confirmation, the estimate
control and the pause dialog; the 44px target and
no-horizontal-overflow floors at a phone and a desktop width. It also
pins the M7C choices a scan cannot see on its own: `aria-pressed` chips
inside a named group, exactly one dialog **and one `dialog-title`** on
the page at a time, and a print ticket that is in the document but out
of the accessibility tree.

**Two corrections the acceptance found in the M7C board.**

1. **The drawer could be dismissed only with Escape.** The board is a
   counter-top tablet surface and every other dialog in the control
   center offers a visible way out; a device with no keyboard could not
   put an order down again. It now carries a `Close` control in every
   state — including the one where the detail failed to load, which
   previously offered no control at all.
2. **The new-order live region was `display: none` while empty**, which
   takes it out of the accessibility tree entirely — so the first
   arrival would have been a region _appearing_ rather than a region
   _updating_, exactly what ruling D10 asks it not to be. It is
   visually hidden instead, and the acceptance spec now finds it **by
   role**, in a real browser with the real stylesheet, before anything
   arrives.

Verification: Playwright **31** (from 29), control-center **515** (from
513 — the drawer's two dismissal tests), backend **1,320** (from 1,319
— the race proof); api-client 115, renderer 165, storefront 146,
contract 89 operations, and the storefront budget all unchanged, the
storefront being untouched. Ruff, format, mypy, typecheck, lint,
prettier, builds, budget, CSS, contract and built-server verification
green.
Merge evidence: PR #67, reviewed head
`ff6244f30814bea78f83b275ef2cbd42bdcad169`, SHA-bound merge
`bacde45710fa4c3a39898a0245220596eccb3564` (parents `ec329071` then the
reviewed head; merge tree `aadc4e12` equal to the reviewed head tree);
exact-head CI run `30857565174` and exact-merge push CI run
`30857933978` both green — five jobs, zero artifacts, attempt 1,
**including the `frontend` job that carries retained risk 1**.
