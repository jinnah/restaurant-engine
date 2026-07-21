# 03 — Domain Rules

Summarizes blueprint §§7, 9, 14. The blueprint is authoritative.

These rules become binding when their domain is implemented (Milestone 2
onward). They are recorded now so implementation milestones code against a
stated contract instead of rediscovering it. **No domain below exists in code
during Milestone 0.**

## Domain map

| Domain     | Owns                                                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity   | Users, credentials, sessions, memberships, roles, password reset                                                                                  |
| Businesses | Businesses (the tenant aggregate, ADR-012), status, slug, locale/currency/timezone defaults, entitlements, design assignment, domains, onboarding |
| Catalog    | Categories, items, modifier groups/options, availability, pricing, sorting, featured status, dietary attributes, public menu projections          |
| Storefront | Design variants, section registry, section content, draft/published versions, publication history, public projection                              |
| Media      | Upload validation, metadata, tenant storage keys, variants, deletion policy                                                                       |
| Hours      | Weekly schedules, exceptions, pickup windows, preparation time, throttling, next-valid-pickup-time                                                |
| Orders     | Checkout validation, numbering, snapshots, totals, status transitions, projections                                                                |
| Audit      | Append-only security and business events                                                                                                          |

## Identity and access

Roles: `platform_admin`, `owner`, `manager`, `staff`. Authorization is
expressed as **named capabilities** (for example `menu.write`,
`orders.advance`) mapped from roles in one policy module — never scattered
role-string comparisons.

**Implemented in M2A (ADR-010):** `users` (normalized-email identity,
Argon2id hashes, backoff state, `is_active` kill-switch), `sessions`
(opaque hashed tokens, per-session CSRF token), and the login/logout/
session workflows in the identity application service. `platform_admin`
is a user flag, not a membership. Accounts are created only by the
`create_platform_admin` bootstrap CLI until onboarding (M2D). Password
policy (12–128 chars) applies when setting passwords, never at login.
Self-service password reset is deferred to the first email channel (M6 at
the earliest); the interim recovery path is a platform-admin-issued
single-use reset token (M2D).

**Implemented in M2D (ADR-014):** invitation acceptance is the product
path that creates member accounts (the CLI remains platform-admin
bootstrap and break-glass). Identity owns `password_reset_tokens` —
single-use, SHA-256-stored, database-clock expiry, one live token per
user — issued only by `platform.users.recover` (account-takeover-
equivalent authority: audited, no public issuance) and redeemed publicly
with a two-phase Argon2 guard; successful redemption resets backoff
state and revokes every session. Identity also exposes the narrow
no-commit creation functions the businesses onboarding service uses, so
identity stays the sole owner of user/membership writes.

## Businesses (the tenant aggregate)

One **Business** is one tenant (ADR-012): one storefront, its own
memberships, currency, and timezone. Restaurants are the first vertical;
vertical differences are expressed through reusable platform capabilities
and configuration, never customer-specific code. Tenant status is a state
machine:

```text
provisioning → active → suspended → active
                         └────────→ closed
```

Permanent deletion is a separate, heavily restricted operational process;
the normal platform action is suspension or closure.

**Implemented in M2B (ADR-011, amended by ADR-012):** businesses owns
`businesses` and this lifecycle; identity owns `memberships` and the
capability policy. Closure is reachable **only** through
`suspended → closed`; `closed` is terminal. Every transition runs under a
row lock, is audited, and rejects illegal transitions with 409
`invalid_state`. **Owner invariant:** `provisioning` may have zero owners;
entering `active` (activate or reactivate) requires at least one owner;
`suspended` retains its owners; `closed` retains its historical
memberships. The removal/demotion-side guard ships with the first
milestone that introduces membership removal (not M3). Public tenant
resolution and public suspension behavior are M2C. Authorization: platform
operations require the `platform.businesses.manage` capability (conferred
by `users.is_platform_admin`, never a membership); business-scoped reads
require `business.view` (a membership role). Nonmember/nonexistent → 404
(existence non-disclosure); member lacking capability → 403.

**Implemented in M2D (ADR-014):** businesses owns `business_invitations`
(onboarding state: one live invitation per business + normalized email,
role ceiling on issue/replace/revoke, platform bootstraps the first
owner, revocation works in any status, uniform neutral 404 for every
invalid public redemption, no auto-login) and `feature_entitlements`
(append-only code registry seeded `online_ordering`; platform-only
full-set PUT, closed businesses immutable; members read their effective
set; unknown stored keys are fail-closed). Existing users join additional
businesses through the authenticated, email-bound acceptance endpoint.

## Catalog

- All prices are integer minor units; currency comes from the tenant.
- Modifier `min_select` ≤ `max_select`; `max_select` cannot exceed the count
  of selectable active options unless null (unlimited).
- Option price delta is zero or positive initially.
- Featured-item count is governed by a centralized tenant policy.
- "Sold out today" and "hidden" are separate states.
- Reorder operations run transactionally and normalize positions.
- Deleting an entity referenced by an order snapshot is safe because
  snapshots are immutable.

**Implemented in M3A (ADR-017):** catalog owns `menu_categories`,
`menu_items`, and `menu_item_dietary_tags` (registry seeded
`halal`/`vegetarian`/`vegan`, canonical lowercase, fail-closed reads).
Every write runs under the Business row lock after a membership
capability check (`business.catalog.write` owner/manager; the separate
availability command additionally reachable by staff via
`business.catalog.availability`); provisioning/active/suspended
businesses are editable, closed are immutable. Positions are dense
0..n-1 per scope with DEFERRABLE DB uniques; reorders are full-set,
exact-set-validated, atomic, idempotent. Names normalize
(trim/collapse/NFC) with case-insensitive DB uniqueness (categories per
business, items per category). Centralized limits: 50 categories, 300
items/business, 100 items/category, 6 featured (hidden items count;
hiding never clears the flag), 3 dietary tags/item; prices are
0–10,000,000 minor units (F1 ruling), DB-CHECK-enforced. Categories
delete only when empty. Nine audit actions record every mutation in its own
transaction.

**Implemented in M3B (ADR-017):** catalog also owns `modifier_groups`
(per-item, min/max selection rules with a DB-enforced 0-30 numeric
domain, NULL max = unlimited) and `modifier_options` (per-group, price
delta 0-10,000,000 minor units DB-enforced, `is_available` operator
toggle). Satisfiability — at least one available option, min
reachable, finite max not above available options — is computed and
report-only: admin construction is never blocked, and every group
response carries `active_option_count` + `is_satisfiable`. Limits: 10
groups/item, 600 groups/business, 30 options/group, 3000
options/business. Same authorization as the rest of the catalog
(owner/manager write; staff read-only — no modifier authority);
identical no-op-suppressed exact-set reorders (M3A reorders aligned per
R-1). Group deletion cascades options with one audited event; item
deletion cascades without modifier-event fan-out.

**Public menu projection (M3D, ADR-017).** `GET /api/v1/public/menu` is
the unauthenticated, Host-resolved projection of the catalog; only
**active** Businesses have one, and every failure is the neutral 404.
Persisted validity and public availability are separate concerns: the
database decides what may be stored, the projection decides what a guest
may currently see and order, and nothing in it is a write gate.

- Invisible categories and hidden items are excluded; a category left
  with no publicly eligible item is suppressed rather than shown empty.
- Sold-out items stay listed (`is_available = false`); "sold out" and
  "hidden" remain separate states.
- Unavailable modifier options are omitted. An **unsatisfiable optional**
  group is omitted harmlessly; an **unsatisfiable required** group is
  omitted and makes the item `is_orderable = false` — the item stays
  listed and priced, because hiding is an explicit administrative state
  and a transient option toggle should not remove an indexed page.
  Satisfiability is the same `is_group_satisfiable` policy the admin
  projection uses — one formula, two projections.
- `is_orderable` is true only when the item is available and every
  required group is satisfiable. M6 remains authoritative at order time;
  these are display facts, not a checkout guarantee.
- Prices are integer minor units and the currency appears once, from the
  Business. Dietary reads stay registry-filtered.
- Ordering is explicit everywhere with stable id tie-breakers; array
  order is the contract, so no `position` is exposed. Items appear
  exactly once, inside their category, and `featured_item_ids` references
  those canonical representations by id rather than duplicating them.
- Public schemas are separate types, never administrative ones, so
  management-only fields cannot leak by default.

## Storefront composition

Versioned, schema-validated configuration:

```json
{
  "schema_version": 1,
  "theme": { "accent": "#A34B2A" },
  "sections": [
    { "id": "hero-main", "type": "hero", "enabled": true, "props": {} }
  ]
}
```

- The platform controls structural variants and available capabilities;
  restaurant users control content, media, ordering, and visibility within
  validated boundaries.
- Publication is transactional; at most one draft and one published version
  per tenant. Publishing archives the previous published version and seeds
  the next draft. Restoration creates a new version; history is immutable.
- Every persisted config validates against the schema registry; every
  published config must be renderable by the deployed storefront.

## Media

Business domains store **media identifiers, not filesystem paths**, behind a
narrow storage protocol — runtime `put` / `open` / `delete` / `stat`, plus a
maintenance-only `iter_objects` extension for operator tooling (ADR-017 M3C
ruling; the blueprint's earlier `public_url` sketch is superseded — delivery
URLs are built from opaque asset ids and logical variant names outside the
adapter, and internal keys never leave storage/sweep code). Minimum controls:
content-type and file-signature validation, dimension/byte limits, randomized
tenant-prefixed keys, safe re-encoding to strip metadata, orphan detection,
server-generated responsive variants.

**Implemented in M3C (ADR-017):** media owns `media_assets` (immutable
identity; `kind` = `image` for now; `status` pending/active on the database
clock — pending expires 48 h after upload, expiry compares `now()` in SQL,
at equality the asset is expired) and `media_asset_variants` (relational
320/640/1280 rows, each with size and checksum of the bytes actually
retained). The canonical stored asset is the re-encoded WebP (EXIF
orientation applied, ≤ 2560 px longest side, quality 82 method 4 lossy,
alpha preserved, all metadata stripped); the original upload is not
retained. Static JPEG/PNG/WebP only. Limits: 500 assets/business
(pending + active), 1 GiB stored bytes/business, 32 MiB combined encoded
output per asset, upload file cap 10 MiB default / 20 MiB deployment
maximum — all checked under the Business row lock from authoritative rows
(no denormalized totals). `business.media.write` (owner/manager) mutates;
every member reads/previews; the platform holds no membership (404).
Menu items attach at most one image through a composite RESTRICT FK with
contextual alt text (≤ 300; alt requires image); attach/replace/clear/alt
is one catalog command with exact no-op suppression; first valid
attachment promotes pending → active (one-way); ever-attached assets are
never auto-deleted; referenced assets cannot be deleted. Expired
never-attached pending assets are cleaned by the operator sweep CLI
regardless of business lifecycle (system maintenance, NULL-actor audit);
rows whose objects are missing are report-only, always.

**Public delivery (M3D, ADR-017).**
`GET /api/v1/public/media/{asset_id}/{variant}` serves the canonical WebP
or one of its responsive variants, addressed by opaque asset id and
logical variant name — never a storage key, path, or checksum. Delivery
requires **every** condition to hold now: an active Host-resolved
Business, a same-Business asset, `status = 'active'`, the representation
present in the database inventory, and at least one non-hidden menu item
in a visible category referencing it. Active status alone is deliberately
insufficient — promotion is one-way, so a detached asset would otherwise
stay retrievable forever by anyone holding its URL. Sold-out and
non-orderable items still authorize their image. Every ineligible case
returns the same neutral 404, and the public menu never advertises a URL
for an asset it did not confirm active while assembling the projection.

Validators are strong derived ETags over the checksum of the exact
delivered representation; the stored checksum itself is never returned.
`If-None-Match` supports `*`, comma-separated lists, and weak comparison,
and a matching validator still verifies eligibility, inventory, and the
physical object before answering 304 — it just never reads the bytes. The
object is opened before any response header is committed, so an object
that vanishes between verification and read is a clean 404 rather than a
truncated 200. Delivery detects a **missing object** and a **byte-size
disagreement**; it does not hash per request, so same-size corruption is
detected by `sweep_media.py --verify` and the backup preflight, and is
never claimed as a delivery-time guarantee. `Range` is ignored (the full
representation is returned, `Accept-Ranges` is never advertised) and
`Last-Modified`/`If-Modified-Since` are deliberately unsupported, because
restoring the media root rewrites filesystem timestamps.

## Hours and fulfillment

Hours are structured local time plus tenant timezone — never freeform
storefront text. Instants are computed carefully across DST transitions.
Order timestamps are stored in UTC alongside the tenant timezone used for
display.

## Orders

Status machine:

```text
submitted → accepted → preparing → ready → completed
     ├──────────────→ rejected
     └──────────────→ cancelled
```

Every transition is permission-checked, state-validated, timestamped, and
audited. Checkout: the server recalculates all prices (client totals are
display hints); availability and modifier rules are revalidated; the order
stores item/option/price/tax/display-name snapshots; totals are integer minor
units; an idempotency key prevents duplicates; order creation and outbox
notification commit together; public tracking uses a high-entropy token.

## Audit

Append-only events capturing actor, tenant, action, target, timestamp,
correlation ID, and a safe structured summary. Never passwords, session
tokens, card data, or unnecessary customer data.

**Implemented foundation (M2A):** `audit_events` written by a single
recorder inside the same transaction as the change it records. Action
names live in an append-only code registry; `details` payloads are built
only from per-action typed schemas (closed, denylist-tested key set).
First actions: `auth.login_succeeded`, `auth.login_failed`,
`auth.login_throttled`, `auth.logout`, `user.platform_admin_created`.
M2B adds the business lifecycle actions `business.created`,
`business.activated`, `business.suspended`, `business.reactivated`,
`business.closed`, tenant-scoped via `audit_events.business_id`.
M2D adds invitation (`business.invitation_issued/revoked/accepted`),
entitlement (`business.entitlement_granted/revoked`), and recovery
(`auth.password_reset_issued/completed`) actions, plus the read APIs
(ADR-014): a platform stream (`platform.audit.read`) and a business
trail (`business.audit.read`, owner/manager) with exclusive-cursor
pagination and **typed read-time detail projections** — stored JSON is
never returned verbatim.

## Data model policies (blueprint §9)

- UUID primary keys generated consistently; timezone-aware UTC timestamps.
- Money: signed 64-bit integer minor units with nonnegative checks where
  applicable.
- Optimistic concurrency on high-conflict editable resources.
- Soft deletion only where recovery/audit semantics require it.
- Tenant-scoped, non-secret order numbers; random revocable public order
  tokens; normalized canonical email.
- JSONB limited to versioned storefront composition, provider payload
  envelopes, or genuinely variable metadata.

## Transactions and asynchronous work

An application service owns one business transaction; repositories never
commit. External network calls do not occur inside an open transaction
unless unavoidable and documented. The transactional outbox arrives with
orders (Milestone 6); the order board begins with short polling.
