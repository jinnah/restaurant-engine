# ADR-027: Restaurant order operations (Milestone 7)

- **Status:** Accepted — M7A delivered (2026-08-02); M7B–M7D not started
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
