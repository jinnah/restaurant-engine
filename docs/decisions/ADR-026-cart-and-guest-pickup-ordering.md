# ADR-026: Cart and guest pickup ordering (Milestone 6)

- **Status:** Accepted — M6A delivered (2026-08-02); M6B–M6D not started
- **Date:** 2026-08-02
- **Deciders:** Jinnah (product owner / principal architect), Claude (senior engineer)

Prepared against `main` @ `b01c93f1` (Milestone 5 complete), reviewed
2026-08-02 with four amendments recorded inline (D9 narrowed to
self-origin; D10 scoped to placement and slots; replay wording corrected
to current-representation; the tracking projection stripped of customer
fields). Authority: blueprint §7.7, §9, §10, §11, §12.1, §14, §19 (M6);
docs/08's strengthened 2026-07-23 commercial commitments; ADR-025's
recorded M6 obligations (throttling D3, UTC-plus-tenant-timezone order
timestamps, first consumption of the pickup-slot service).

---

## 1. Context — what exists and what M6 must create from nothing

Every seam M6 needs was verified in the delivered code:

- **Catalog** exposes the public menu projection with `is_orderable` as a
  _display fact_ ("M6 remains authoritative at order time" is already in
  the schema docstring). The satisfiability formula is one function
  (`catalog/policies.is_group_satisfiable`), prices are DB-checked integer
  minor units, and **no pricing helper exists anywhere** — Orders owns the
  first one.
- **Hours** ships `pickup_slots(now, *, weekly, exceptions, policy, tz,
limit)` — pure, tested, and deliberately consumerless; `effective_policy`
  is already actor-free and public-safe. `hours/models.py` records that
  order throttling is absent by ruling D3 and owned by M6.
- **Entitlements** exist (`online_ordering` seeded since M2D) but every
  read demands an authenticated actor. There is **no anonymous
  entitlement check** and no public projection exposes any
  entitlement-derived fact.
- **Anonymous unsafe requests** have one mechanism:
  `require_browser_context` (Sec-Fetch-Site → Origin allowlist → Referer,
  fail-closed), used by invitation acceptance. The synchronizer-token
  layer requires a session and does not apply to guests.
- **Audit** supports NULL actors natively (the recorder's
  `actor_user_id: uuid.UUID | None`); adding actions is enum + typed
  details + read-projection entry.
- **Outbox and idempotency infrastructure do not exist** — zero matches
  repo-wide. M6 introduces both tables from scratch.
- **The storefront has zero client JavaScript of its own**: the `'use
client'` allowlist contains exactly `app/error.tsx`, the tenant
  transport hard-refuses non-GET/HEAD, the dev API forwarder exports only
  GET/HEAD, and the app has no state-management dependency. The first-load
  JS ceiling is 502,201 B against a 456,547 B baseline (~45.6 KB of
  headroom).
- Per-IP rate limiting remains an M8 reverse-proxy item (the M3D
  precedent: an application limiter would key on a spoofable source).

M6 does **not** include: the restaurant order board or any staff status
command (M7), online payments or refunds, delivery, email/SMS channels,
customer accounts, or promotions (M9 — but its snapshot fields are
reserved now, per the reconciliation).

## 2. Decision summary

Milestone 6 is delivered as a new `orders` domain
(`backend/app/domains/orders/`) owning the blueprint §9 tables (`orders`,
`order_lines`, `order_line_options`, `order_status_events`,
`idempotency_keys`) plus the platform-global `outbox_messages`; a **pure
cart validation and pricing core** that consumes an explicit catalog
checkout view (never catalog's ORM models); an idempotent, transactional
checkout service that consumes the M5 pickup-slot service and enforces
per-slot throttling (D3); a public placement/tracking/cancellation API
under the established host-resolution and neutral-404 contract; and the
storefront's first client islands — the cart, the modifier picker, the
checkout form, and the order tracker — inside the existing JS budget with
**no new runtime dependency**. Delivery is four separately authorized
slices (§13) under the rulings in §12.

### Domain boundaries

`orders` depends on `businesses` (resolution, lifecycle, currency,
timezone), `catalog` (a new explicit _checkout view_ read interface),
`hours` (the pure slot service + `effective_policy`), and `audit`. The
dependency is one-directional: catalog and hours never import orders.
Cross-domain reads go through named service functions, never through
another domain's models (blueprint §6.2). The storefront domain is
touched only to extend `HeroAction` (§8's recorded seam) — the ordering
_surface_ lives in `apps/storefront`, gated on a new public fact (§5).

## 3. Data model

All tables tenant-leading (`business_id` first in every index and unique)
except `outbox_messages` (platform-global, documented as such). One
additive migration in M6A; nothing existing is altered except one new
nullable column on `fulfillment_settings` (D3).

**`orders`** — one row per placed order, immutable except `status`:
`id` (UUIDv7), `business_id` (FK RESTRICT), `order_number` (int, unique
per business, dense from 1, non-secret), `tracking_token_digest`
(SHA-256, unique; the token itself is returned exactly once at
placement), `status` (enum: M6 knows `submitted` and `cancelled`; the
enum ships with M7's full set so the DB type is stable — but the M6
service can only produce these two), `placed_at` (timestamptz UTC),
`business_timezone` (snapshot of the tenant zone at placement — the
ADR-025 obligation: UTC instant plus the timezone used for display),
`customer_name`, `customer_phone`, `customer_email` (nullable),
`order_instructions` (nullable), `consent_updates` (bool),
`consent_marketing` (bool), `pickup_kind` (enum `asap` | `scheduled`),
`promised_pickup_at` (timestamptz), `currency` (snapshot, CHAR(3)),
`subtotal_minor`, `tax_minor`, `total_minor` (BIGINT, CHECKed
nonnegative; §12 D6 constrains `tax_minor = 0` in M6), and the
**reserved promotion snapshot fields** (D7): `discount_total_minor`
(BIGINT, CHECKed `= 0` until M9) and `applied_promotions` (JSONB, CHECKed
`= '[]'` until M9) — so historical orders already carry the columns M9
will populate and never change retroactively.

**`order_lines`** — the immutable item snapshot: `id`, `business_id`,
`order_id` (composite tenant-safe FK to `orders(business_id, id)`,
CASCADE), `position`, `item_provenance_id` (bare UUID, **no FK** — D1:
snapshots must survive catalog deletion), `display_name`,
`base_price_minor`, `quantity` (CHECK 1–50), `item_instructions`
(nullable), `line_total_minor`.

**`order_line_options`** — the modifier snapshot: `id`, `business_id`,
`line_id` (composite FK, CASCADE), `position`, `group_provenance_id` and
`option_provenance_id` (bare UUIDs, no FK), `group_display_name`,
`option_display_name`, `price_delta_minor`.

**`order_status_events`** — append-only: `id`, `business_id`, `order_id`
(composite FK), `from_status` (nullable — the creation event has none),
`to_status`, `actor_kind` (enum `customer` | `member` | `system`),
`actor_user_id` (nullable), `occurred_at`. Placement writes the
`→ submitted` event in the same transaction.

**`idempotency_keys`** — `id`, `business_id`, `operation` (Text,
`'order.place'` for now), `idempotency_key` (client-supplied UUID),
`request_digest` (SHA-256 of the canonical payload), `order_id`
(nullable composite FK), `created_at`. Unique `(business_id, operation,
idempotency_key)` — the §9.2 invariant.

**`outbox_messages`** — platform-global by design (a future worker
claims across tenants): `id`, `business_id` (nullable FK), `topic`
(`'order.placed'`), `payload` (JSONB — **ids and facts only, no PII**:
order id, business id, order number, placed_at), `status`
(`pending`/`processed`/`dead`), `attempts`, `next_attempt_at`,
`created_at`, `processed_at`. Unique `(topic, order_id)` where harmful
duplication is possible (§9.2).

Conventions follow the house pattern exactly: `op.f()` constraint names,
CHECK bounds mirrored in `policies.py` with pinned tests, composite FKs
per docs/04, additive-only migration with a dev-only downgrade.

## 4. The checkout flow (the milestone's substance)

**A pure core, the M5 discipline.** `orders/pricing.py` (name
illustrative) is pure: given the _catalog checkout view_ (a frozen
snapshot of the relevant items/groups/options that catalog assembles
through a new explicit service function) and the submitted cart, it
either returns a fully priced, fully snapshotted order draft or a typed
list of line-level failures. Rules, all server-authoritative:

- every referenced item must be publicly visible, in a visible category,
  `is_available`, and every required group satisfiable — the same
  formula the projection uses, revalidated at order time;
- every selected option must exist, be available, and belong to a group
  of the referenced item; per-group selection counts must satisfy
  `min_select`/`max_select`; duplicate option selections rejected;
- prices are recomputed from current catalog rows: `line_total =
(base + Σ deltas) × quantity`; `subtotal = Σ line_totals`;
  `total = subtotal` (D6); client-sent amounts are never used in
  arithmetic;
- bounds: 1–50 quantity, ≤ 30 lines, ≤ 4,000,000,000 minor-unit total
  guard (BIGINT headroom is vast; the guard is defence in depth);
  instructions are normalized, control-free plain text (item ≤ 200,
  order ≤ 500 — blueprint §7.7: never operational instructions to the
  system);
- customer fields: name required (≤ 120), phone required (≤ 40, the
  contact-section precedent — bounded plain text, no deliverability
  claim), email optional (≤ 254); both consents are independent required
  booleans (D7);
- a required `expected_total_minor` must equal the recomputed total, or
  the command fails with `409 price_changed` carrying the authoritative
  totals (D8) — display hints are hints, but a silent price change at
  submit is a trust failure.

**Pickup promise.** `pickup_kind: 'asap'` requires `asap_enabled` and a
non-null `next_pickup_at` computed at placement (that instant becomes
`promised_pickup_at`). `pickup_kind: 'scheduled'` requires
`requested_pickup_at` to be **recomputed as valid** — the service
re-derives slot validity from the stored schedule and policy via the
same pure `pickup_slots` machinery (equality on the slot instant), never
by trusting a list previously shown to the client.

**Throttling (D3, the ADR-025 obligation).** `fulfillment_settings`
gains nullable `max_orders_per_slot` (NULL = unlimited; CHECK 1–100),
owned by the hours domain per the docs/03 domain map, exposed through
the existing fulfillment PUT/read. Enforcement is the orders service's:
under the Business lock it counts non-cancelled orders with the same
`promised_pickup_at` and refuses the slot with a typed 409
(`slot_full`, carrying nearby alternatives) when the cap is reached.
ASAP orders count against the slot their promise lands on.

**The transaction.** One service function owns it, in order: resolve
active Business (dependency) → entitlement + `pickup_enabled` gate (§5)
→ **idempotency check** (an existing `(business, 'order.place', key)`
row returns the stored order verbatim — a replay is a read, not a
write; same key with a different `request_digest` is `409
idempotency_key_reused`) → assemble the catalog checkout view → pure
validation/pricing → `SELECT … FOR UPDATE` on the Business row (D5:
serializes order numbering and slot counting; the house pattern; pilot
scale makes contention a non-issue and the reconsideration trigger is
recorded) → re-check lifecycle → slot validity + throttle count →
`order_number = MAX + 1` → insert order, lines, options, the
`→ submitted` status event, the outbox message, the idempotency row →
audit `order.placed` (NULL actor, typed details: order id, number,
totals, line count — **never** names, contacts, or notes) → commit. No
external network call exists to hold open (§14.1).

**Duplicate-submission proof (the §19 exit criterion).** Two concurrent
identical submissions: one takes the idempotency-unique insert, the
other observes the unique violation, reloads the winner's order, and
returns it — **one order**, and every replay returns the _current
representation_ of that same order (amended in review: a replay after a
customer cancellation honestly shows `cancelled`; the invariant is one
order per key, never byte-equal bodies). The e2e journey simulates the
retry (blueprint §15.3 journey 4).

## 5. Public API surface and the ordering gate

New public routes (all host-resolved, all `no-store`, all neutral-404
per ADR-013; the placement and cancel POSTs additionally carry
`require_browser_context` — extended per D9):

- `POST /api/v1/public/orders` — placement (§4). Ineligibility —
  missing `online_ordering` entitlement, `pickup_enabled` false, or any
  resolution failure — is the one neutral 404 (D10): a storefront
  without ordering shows no ordering surface, and the API discloses
  nothing more than the page does.
- `GET  /api/v1/public/orders/{tracking_token}` — the customer
  projection: status, order number, placed_at + business timezone,
  pickup promise, snapshot lines (display names, quantities, totals),
  business summary — and **no customer fields** (amended in review: a
  tracking URL is shareable by design, so the projection never returns
  the name, phone, email, consents, or instructions the order stores).
  Token authorization is by possession (the M2D sanctioned-exception-2
  pattern: 256-bit token, digest-stored, compared by digest under the
  host-resolved business — token and Host must both match; every
  failure is the same neutral 404). Not single-use, no expiry in M6.
- `POST /api/v1/public/orders/{tracking_token}/cancel` — customer
  cancellation (D11): legal only from `submitted`, writes the status
  event (`actor_kind = customer`) and audit, idempotent on repeat
  (cancelling a cancelled order returns the order unchanged), refused
  with `409 invalid_state` once M7 moves the order past `submitted`.
- `GET  /api/v1/public/pickup-slots` — bounded enumeration for the
  scheduled-pickup picker (the first real exposure of the M5 slot
  service): at most 100 slots within `max_days_ahead`, ineligible
  hosts/entitlement → neutral 404.

**The ordering gate as a public fact (D12).** `PublicPickup` (on the
availability projection) gains `ordering_enabled: bool` — true iff the
Business holds `online_ordering` **and** `pickup_enabled`. This is
deliberate reuse of M5D: the storefront home already reads availability
on every render, so gating the whole ordering surface costs **zero
additional requests**. A new actor-free entitlement primitive
(`businesses.entitlements.business_has_feature(db, business_id, key)`)
supports it — the first anonymous entitlement read, fail-closed on
unknown keys like the existing reader.

**`HeroAction` (the recorded M6 seam).** The enum gains `ORDER_ONLINE =
"order_online"`; the renderer's exhaustive dispatch renders it as
navigation to `/order` **only when `ordering_enabled` is true**, and
degrades to the plain menu link otherwise — entitlement is a live
platform fact, so the gate is at render time, never frozen into
published content (the D5/ADR-025 lesson applied to entitlements).

## 6. The storefront ordering surface (`apps/storefront`)

The first client islands, per blueprint §12.1 (cart, modifier dialog,
tracker are the named allowed islands):

- **Cart state (D13):** a versioned, per-tenant cart in
  `localStorage` (origin-scoped by the tenant host, so isolation is
  structural), managed by a small reducer — **no Redux, no TanStack, no
  react-hook-form, no zod: zero new runtime dependencies**. The
  persisted schema carries `schema_version`; an unknown version drops
  the cart cleanly (blueprint: cart schema/versioning).
- **Modifier picker:** a client dialog on `/menu` items (rendered from
  the same public menu projection; `is_orderable` finally renders),
  enforcing min/max locally for UX while the server stays authoritative.
- **`/order`:** cart review + checkout form — name, phone, optional
  email, item/order instructions, ASAP or a slot from
  `/public/pickup-slots`, the **two separate consent checkboxes** (D7,
  never pre-checked, never blended), and the expected total. Failure
  states render honestly: per-line stale-item 409s mark the offending
  lines; `price_changed` shows both totals; `slot_full` offers the
  alternatives.
- **Confirmation + `/order/track/{token}`:** placement navigates to the
  tracking page (token in the URL path, the blueprint's own route
  shape); the tracker island polls the public tracking GET at a modest
  interval (M7's board uses the same polling doctrine).
- **Transport (D9):** in production the tenant host serves storefront
  and `/api/v1` same-origin behind the reverse proxy, so island fetches
  are relative same-origin calls and `Sec-Fetch-Site: same-origin`
  satisfies the browser-context check's first branch. In development
  and e2e, the storefront's **development-only** API forwarder gains
  POST for `/api/v1/public/` paths only, forwarding the browser-context
  headers verbatim (it stays production-disabled — the delivered
  behavior, already pinned by the built-server verification). The
  read-only `tenant-fetch` used by SSR is untouched.
- **Budgets:** the islands are component code only; the 502,201 B
  ceiling is **not** raised in this proposal. Each UI slice measures
  first-load JS in its gate; if the islands genuinely cannot fit, the
  ceiling change is its own reviewed ADR-021 amendment with the
  measurement as evidence — never a silent bump. The `'use client'`
  allowlist grows by exactly the island files, each named in the
  delivered test.

Accessibility floors apply as acceptance criteria (§3.8): the cart and
dialogs are keyboard-operable with focus management (the CC dialog
discipline), 44px targets, visible focus, and honest empty/error states.

## 7. The outbox (§14.2) — introduced, not yet pumped

M6 creates `outbox_messages` and writes `order.placed` in the placement
transaction — the durable coupling is the §19 deliverable ("order
creation and outbox notification are committed together"). **No worker
ships in M6** (D14): there is no email/SMS channel and no consumer, and
the project prompt forbids placeholder machinery; rows accumulate as
`pending` (bounded by order volume, visible operationally) until the
first channel milestone ships the poller with its first real handler.
The M7 order board does not need the outbox — it polls orders directly
(§14.3).

## 8. Audit, logging, privacy

New actions: `order.placed`, `order.cancelled_by_customer` (NULL-actor
public events — the recorder already supports this), plus M7's members
later. Typed details carry ids, order number, totals, line count, and
status transition — **never** customer name, phone, email, notes, or
the tracking token (blueprint §7.8/§16.1). Structured logs likewise:
order id and business id, no PII. The tracking token appears exactly
once, in the placement response body.

## 9. Security summary

No new authentication surface. Placement and cancel are anonymous,
browser-context-checked unsafe requests on host-resolved active
businesses; tracking is authorization-by-possession with digest storage;
idempotency keys are tenant-scoped and cannot collide across businesses;
all five order tables are tenant-leading with composite FKs, and the
§8.5 isolation matrix extends to every new resource (a tenant's tracking
token is useless under another tenant's host). Per-IP throttling of the
checkout route remains the recorded M8 reverse-proxy item; what M6
enforces app-side is the D3 per-slot cap, which keys on the business,
not the caller. Input schemas reject extra fields; every text field runs
the normalize/control-character policy; no HTML anywhere.

## 10. What M6 deliberately does not do

No order board, no staff/owner order reads or commands (M7 — including
any CC surface: the control center is untouched except the one
fulfillment throttle field). No payments, refunds, tips, or fees. No
delivery. No email/SMS/notification sending and no outbox worker (D14).
No customer accounts or reorder. No promotions — only the reserved
snapshot columns (D7). No tax computation (D6). No per-IP rate limiting
(M8). No new storefront dependency, no budget raise, no schema_version
bump, no RLS.

## 11. Consequences

Easier afterward: M7 reads a proven order store with an append-only
event trail; M9 finds discount columns already in every historical
snapshot; the first channel milestone finds durable notification intents
already accumulating. Harder/costs: the storefront takes on real client
state for the first time (budget pressure is now a live constraint per
slice); checkout serializes per business on the row lock (fine at pilot
scale; the trigger to revisit is a measured p95 placement latency
problem); pending outbox rows accumulate without a worker (operational
visibility required at M8's monitoring pass); the browser-context
extension (D9) widens a security-relevant policy and needs adversarial
tests.

## 12. Proposed rulings (D1–D14)

- **D1 — Snapshots carry no FK to catalog.** Lines/options store display
  names, prices, and bare provenance UUIDs. Catalog rows stay freely
  deletable (the blueprint's own rule); history can never dangle because
  it references nothing.
- **D2 — Idempotency is a first-class table.** Client-generated UUID key,
  unique per (business, operation); replays return the stored order;
  key reuse with a different payload digest is a typed 409. TTL/cleanup
  deferred to operations (rows are tiny; a retention sweep can join a
  later maintenance pass).
- **D3 — Per-slot throttling, hours-owned setting, orders-owned
  enforcement.** `max_orders_per_slot` (nullable) on
  `fulfillment_settings`, honoring the docs/03 domain map; the checkout
  transaction counts non-cancelled orders per promised slot under the
  Business lock. Discharges ADR-025's D3 obligation.
- **D4 — Tracking tokens follow the M2D token pattern.** 256-bit,
  digest-only storage, possession + Host both required, one neutral 404
  for every failure; not single-use, no M6 expiry.
- **D5 — Checkout takes the Business row lock.** It already needs
  serialization for order numbering (MAX+1) and slot counting; the house
  pattern provides it. Reconsideration trigger: measured placement
  latency under real load.
- **D6 — No tax computation in M6.** `tax_minor` exists and is CHECKed
  to zero; totals equal subtotals; cash-at-store means the register
  remains the money authority at pickup. Alternative (a per-business
  flat rate) rejected for now: US restaurant tax is jurisdiction- and
  item-dependent, and a wrong displayed tax is worse than none.
  Reconsideration trigger: pilot feedback demanding displayed tax, or
  online payments (which make the platform the money authority).
- **D7 — Two independent consents; promotion fields reserved.**
  `consent_updates` and `consent_marketing` are separate, required,
  never-blended booleans recorded on the order; `discount_total_minor`
  and `applied_promotions` exist from day one, CHECK-frozen until M9.
- **D8 — `expected_total_minor` is required.** Mismatch is `409
price_changed` with authoritative totals. The server never uses the
  client number in arithmetic; it uses it to refuse surprises.
- **D9 — Browser-context policy extension: self-origin only (amended in
  review).** The Sec-Fetch-Site same-origin branch already covers modern
  browsers under the production same-origin topology. The Origin
  fallback branch gains exactly one new acceptance: an Origin whose host
  **equals the request's own Host** (host:port comparison; scheme
  enforcement stays with the M8 proxy-trust decision). A "tenant host
  family" rule was considered and rejected in review: it would let one
  tenant's origin satisfy the check for another tenant's host on legacy
  browsers. Self-origin is strictly narrower, covers every tenant host
  generically with no new parser, and behaves identically through the
  dev forwarder (whose forwarded Host equals the browser's origin host).
  The dev-only forwarder gains POST for `/api/v1/public/` only and stays
  production-disabled.
- **D10 — Ineligible ordering is neutral 404 — for placement and slots
  only (amended in review).** Missing entitlement or disabled pickup on
  `POST /public/orders` and `GET /public/pickup-slots` answers exactly
  like an unknown host: the API never discloses a capability the page
  does not show. Tracking and cancellation are deliberately **not**
  entitlement-gated: an order already placed is a fact the customer must
  be able to follow and cancel even after the platform revokes ordering;
  they are authorized by token possession plus host resolution alone
  (suspension still hides everything, as it does everywhere).
- **D11 — Customer cancellation is in M6.** Legal only from `submitted`,
  by tracking-token possession, evented and audited; everything past
  `submitted` is M7's machine and refuses with `invalid_state`. (The
  status enum ships complete so the DB type is stable; M6 code can only
  produce `submitted` and `cancelled`.)
- **D12 — `ordering_enabled` rides the availability projection.** The
  storefront already fetches it on every home render (M5D), so the gate
  is free; the fact is computed live from entitlement + pickup policy
  and is never frozen into published storefront content.
- **D13 — Cart is client-side, versioned, dependency-free.**
  localStorage + reducer, per-tenant by origin; no server cart, no new
  runtime dependency in `apps/storefront`; unknown schema versions drop
  the cart cleanly.
- **D14 — Outbox table and transactional write now; worker deferred.**
  The durable coupling is the M6 deliverable; the poller ships with the
  first real handler (the first channel milestone), not as placeholder
  machinery.

## 13. Delivery slices (each separately authorized, one PR each)

| Slice                                           | Scope                                                                                                                                                                                                                                                                                                                       | Depends on |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **M6A** — Orders domain foundation              | migration (5 order tables + outbox + throttle column), pure validation/pricing core over a new catalog checkout view, checkout service (idempotency, numbering, snapshots, D3 throttling, outbox write, audit), `POST /public/orders`, D9 browser-context extension, anonymous entitlement primitive, contract regeneration | —          |
| **M6B** — Public tracking and the ordering gate | tracking GET + customer cancel + pickup-slots endpoint, `ordering_enabled` on the availability projection, `HeroAction.ORDER_ONLINE` + renderer arm, isolation matrix for the new resources                                                                                                                                 | M6A        |
| **M6C** — Storefront ordering UI                | cart island + persisted schema, modifier picker, `/order` checkout (consents, slots, honest failure states), confirmation + `/order/track/{token}` tracker, dev-forwarder POST, allowlist/budget updates, JSON-LD untouched                                                                                                 | M6A, M6B   |
| **M6D** — E2E and close-out                     | the CC fulfillment-throttle field (the one control-center touch), blueprint journey 4 (customize → order despite a simulated retry) plus cancellation and stale-item journeys, responsive/a11y acceptance for the ordering surfaces, docs close-out and exit-criteria verification                                          | all        |

Exit criteria (blueprint §19): retries do not duplicate; stale/sold-out
items fail gracefully; totals are authoritative; orders survive menu
edits; end-to-end checkout passes.

## 14. Reconsideration triggers

- Measured checkout latency makes the Business-lock serialization (D5) a
  real cost → move numbering to a counter table and throttling to an
  advisory-locked count.
- A channel milestone lands → the outbox worker (D14) ships with it.
- Pilot demands displayed tax or online payments arrive → reopen D6.
- Real deployments show old browsers failing the D9 Sec-Fetch-Site
  branch in volume → revisit the Origin family rule's breadth.
- M9 unfreezes the promotion snapshot columns (D7) by design.

---

## Delivery record

### M6A — Orders domain foundation: delivered, 2026-08-02

Delivered exactly the §13 M6A scope. Migration `e7a2c94d51b8` (from
`c3d8f5a21e47`) lands the five order tables, the platform-global
outbox, and the nullable `fulfillment_settings.max_orders_per_slot`
column — discharging ADR-025's D3 deferral with the hours domain owning
the setting (additive default, so the delivered M5C form stays valid)
and the orders checkout owning the count of non-cancelled orders per
promised slot. The pure pricing core validates and reprices the whole
cart against the new explicit `catalog.checkout_view` interface,
applying the public projection's own orderability formula
authoritatively and collecting every problem before failing; the
placement transaction runs under the Business row lock (D5) and commits
the order, the FK-free snapshot (D1), the `→ submitted` event, the
`order.placed` outbox message (D14 — no worker), the idempotency row
(D2 — replays return the current representation of the one stored
order; reuse with a different payload is `409 idempotency_key_reused`;
the concurrent race resolves to the winner), and the NULL-actor audit
event together. `POST /api/v1/public/orders` is the first unsafe public
route: neutral-404 for every ineligible cause including missing
entitlement or disabled pickup (D10, via the first actor-free
entitlement primitive), guarded by the browser-context check extended
with self-origin acceptance (D9 as amended in review), and pinned by
the public-surface invariant test to carry both guards. Four new error
codes (`cart_stale`, `price_changed`, `slot_unavailable`,
`idempotency_key_reused`); tracking tokens digest-stored and disclosed
exactly once (D4); consents independent (D7); `tax_minor` and the M9
promotion columns present and CHECK-frozen (D6/D7); `placed_at` UTC
plus `business_timezone` records the ADR-025 timestamp pair. Contract
**74 → 75** (`public_order_place`); the public facade gains
`placeOrder()`.

One implementation note worth recording: the orders mappers declare no
`relationship()` links by design (snapshots are data, not an object
graph), and SQLAlchemy's unit of work orders INSERTs by relationship
dependency — bare FK metadata alone does not sequence mappers — so the
placement transaction pins parent rows with explicit flush points.

Verification: backend **1,290** (from 1,245 — the pure
pricing/staleness matrix, the placement schema text policy, the full
browser-context suite including every D9 rejection case, and the
placement API matrix covering the transactional record, PII-free audit
and outbox payloads, idempotent replay and key reuse, authoritative
totals, stale-cart problems, scheduled-slot revalidation, the slot cap
counting non-cancelled orders, neutrality, browser-context enforcement,
and cross-tenant isolation); api-client **112** (from 109); every other
suite, budget, and build gate unchanged and green; `pnpm e2e` 25.
Merge evidence: PR #52, reviewed head `f4f73f84`, SHA-bound merge
`77f2b73e8eb6d4c5c64c2d3ae05ec80945b519b9` (parents `b01c93f1` then the
reviewed head; merge tree `34bb67a0` equal to the reviewed head tree);
exact-head CI run `30761169052` and exact-merge push CI run
`30761377392` both green 5/5 with zero artifacts on attempt 1.

Deliberately not delivered (their own slices): tracking, cancellation,
the public slot listing, `ordering_enabled`, and `HeroAction` (M6B);
the storefront ordering UI (M6C); the CC throttle field and the
ordering journeys (M6D); the outbox worker (D14 — the first channel
milestone).
