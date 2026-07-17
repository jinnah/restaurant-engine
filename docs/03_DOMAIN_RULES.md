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
single-use reset link (M2D).

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
narrow storage protocol (`put` / `delete` / `public_url`). Minimum controls:
content-type and file-signature validation, dimension/byte limits, randomized
tenant-prefixed keys, safe re-encoding to strip metadata, orphan detection,
server-generated responsive variants.

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
