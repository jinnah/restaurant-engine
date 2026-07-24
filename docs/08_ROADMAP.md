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

| Milestone                                                      | State                                            |
| -------------------------------------------------------------- | ------------------------------------------------ |
| M0 — Architecture and repository contract                      | **Complete** (2026-07-14)                        |
| M1 — Platform foundation                                       | **Complete** (2026-07-15)                        |
| M2 — Identity, tenancy, and onboarding                         | **Complete** (2026-07-19)                        |
| M3 — Catalog and media                                         | **Complete** (2026-07-23)                        |
| M4 – M8 — Storefront, hours, ordering, operations, pilot       | Not started                                      |
| M9 – M11 — Commercial growth (promotions, campaigns, Facebook) | Not started (planned; reconciliation 2026-07-23) |

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

M4 has not started. The future commitments recorded by the reconciliation
(customer ordering and order management, promotions and checkout-integrated
discounts, pop-up campaigns, Facebook Page publishing, the expanded Control
Center, and later notifications/payments/delivery/POS/reporting) remain future
work in milestones M4—M11 and are not implemented by this close-out.

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
history, server-rendered storefront, SEO basics, English/Bengali rendering
verification. **Exit:** invalid config cannot save; published config always
renders; draft is never public; performance/accessibility budgets pass.

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
